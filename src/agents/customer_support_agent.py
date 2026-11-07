"""Customer-support agent backed exclusively by explicitly selected real LLMs."""

from __future__ import annotations

import logging
import re
from time import perf_counter

import httpx
from langchain.agents import create_agent
from langchain.agents.middleware import (
    HumanInTheLoopMiddleware,
    ModelRequest,
    ModelResponse,
    after_agent,
    before_agent,
    before_model,
    wrap_model_call,
    wrap_tool_call,
)
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.tools import BaseTool
from langchain_ollama import ChatOllama
from langchain_openai import ChatOpenAI
from langgraph.config import get_config
from langgraph.graph.state import CompiledStateGraph

from agents.lazy_agent import LazyLoadingAgent
from core import settings
from core.llm import get_model
from customer_support.errors import CustomerSupportModelError
from customer_support.mcp_client import load_business_mcp_tools
from customer_support.prompts import SYSTEM_PROMPT
from customer_support.routing import (
    PLANNER_PROMPT,
    ROUTER_PROMPT,
    Intent,
    Plan,
    Route,
    RoutedState,
    allowed_actions,
    missing_fields,
    next_task,
    simple_plan,
    task_guidance,
    validate_plan,
    validated_route,
)
from customer_support.tools import CUSTOMER_SUPPORT_TOOLS
from customer_support.trace import safe_args, safe_route, safe_tool_result, trace_event
from memory.compaction import get_compactor
from memory.context_compaction_candidate import CandidateBudget, CompactedContextAssembler
from memory.context_manager import ContextManager, TokenBudget, count_tokens
from schema.models import DeepseekModelName, FakeModelName, OllamaModelName

logger = logging.getLogger(__name__)


def _forced_tool_for_message(message: str) -> str | None:
    """Route clear business intents deterministically; leave ambiguous ones to the LLM."""
    text = re.sub(r"\s+", "", message.lower())
    has_order_id = bool(re.search(r"(?:ord|ol)\d{4,6}", text, re.IGNORECASE))
    has_phone_last4 = bool(re.search(r"(?:手机|手机号|后四位)[^\d]{0,8}\d{4}", text))

    if has_order_id and has_phone_last4:
        if any(term in text for term in ("退款", "退货", "能退", "资格")):
            return "check_refund_eligibility"
        if any(term in text for term in ("查询", "状态", "物流", "延迟", "到哪")):
            return "get_order_status"

    policy_terms = (
        "政策",
        "规则",
        "条件",
        "七天无理由",
        "发票",
        "保修",
        "质保",
        "换货",
        "补发",
        "取消订单",
        "退款到账",
        "收货地址",
        "修改地址",
        "支付失败",
        "重复扣款",
        "优惠券",
        "促销",
        "隐私",
        "验证码",
        "投诉",
        "维修",
        "人工客服",
        "真人客服",
    )
    if not has_order_id and any(term in text for term in policy_terms):
        return "search_policy"
    return None


@wrap_model_call
async def deterministic_tool_routing(
    request: ModelRequest,
    handler,
) -> ModelResponse:
    """Force a tool only when the latest user intent and required fields are clear."""
    state_messages = request.state.get("messages", []) if request.state else []
    messages = state_messages or request.messages
    if not messages:
        logger.debug("Deterministic routing inspected: no messages")
        return await handler(request)

    latest_message = messages[-1]
    content = latest_message.content
    logger.debug(
        "Deterministic routing inspected: message_type=%s, content_type=%s",
        type(latest_message).__name__,
        type(content).__name__,
    )
    if not isinstance(latest_message, HumanMessage):
        return await handler(request)
    if not isinstance(content, str):
        return await handler(request)
    tool_name = _forced_tool_for_message(content)
    logger.debug(
        "Deterministic routing candidate: tool=%s, content_length=%d",
        tool_name,
        len(content),
    )
    if tool_name is None:
        return await handler(request)

    selected_tools = [tool for tool in request.tools if getattr(tool, "name", None) == tool_name]
    if not selected_tools:
        return await handler(request)
    logger.info("Deterministic tool routing selected: %s", tool_name)
    return await handler(
        request.override(
            tools=selected_tools,
            tool_choice=tool_name,
        )
    )


@before_agent
def log_agent_start(state, runtime):
    logger.info("Customer support request started")
    return None


@after_agent
def log_agent_end(state, runtime):
    logger.info("Customer support request finished")
    return None


@wrap_model_call
async def log_model_call(request, handler):
    started = perf_counter()
    try:
        response = await handler(request)
    except Exception as exc:
        logger.exception("Customer support model call failed error_type=%s", type(exc).__name__)
        trace_event(
            "llm",
            status="failed",
            error_type=type(exc).__name__,
            duration_ms=round((perf_counter() - started) * 1000, 1),
        )
        raise CustomerSupportModelError() from exc
    messages = getattr(response, "result", [])
    if not isinstance(messages, list):
        messages = [messages]
    usage = next(
        (
            getattr(message, "usage_metadata", None)
            for message in reversed(messages)
            if getattr(message, "usage_metadata", None)
        ),
        None,
    )
    trace_event(
        "llm",
        status="completed",
        duration_ms=round((perf_counter() - started) * 1000, 1),
        tokens={
            key: usage[key]
            for key in ("input_tokens", "output_tokens", "total_tokens")
            if usage and key in usage
        },
    )
    logger.info(
        "Customer support model call completed duration_ms=%.1f", (perf_counter() - started) * 1000
    )
    return response


@wrap_tool_call
async def log_tool_call(request, handler):
    name = request.tool_call["name"]
    started = perf_counter()
    try:
        response = await handler(request)
    except Exception as exc:
        logger.exception(
            "Customer support tool failed name=%s error_type=%s", name, type(exc).__name__
        )
        trace_event(
            "tool",
            name=name,
            arguments=safe_args(request.tool_call.get("args", {})),
            status="failed",
            error_type=type(exc).__name__,
            duration_ms=round((perf_counter() - started) * 1000, 1),
        )
        raise
    trace_event(
        "tool",
        name=name,
        arguments=safe_args(request.tool_call.get("args", {})),
        status="completed",
        result=safe_tool_result(name, response),
        duration_ms=round((perf_counter() - started) * 1000, 1),
    )
    logger.info(
        "Customer support tool completed name=%s status=%s duration_ms=%.1f",
        name,
        getattr(response, "status", "completed"),
        (perf_counter() - started) * 1000,
    )
    return response


def routing_middleware(model: BaseChatModel):
    """Run one structured route per user turn; plan only complex turns."""

    @before_agent(state_schema=RoutedState, can_jump_to=["end"])
    async def route_request(state, runtime):
        messages = state.get("messages", [])
        if not messages or not isinstance(messages[-1], HumanMessage):
            return None  # Checkpoint resume; do not call the router again.
        query = str(messages[-1].content)
        history = [m for m in messages if isinstance(m, HumanMessage)][-4:]
        try:
            routed = await model.with_structured_output(Route, method="function_calling").ainvoke(
                [SystemMessage(content=ROUTER_PROMPT), *history]
            )
            route = validated_route(Route.model_validate(routed), history)
            if (
                route.conditional
                and Intent.REFUND in route.intents
                and Intent.REPAIR in route.intents
            ):
                route.intents.insert(0, Intent.ORDER)
            missing = missing_fields(route)
            if missing:
                trace_event("router", result=safe_route(route), missing_fields=missing)
                return {
                    "route": route.model_dump(mode="json"),
                    "plan": {},
                    "task_trace": [],
                    "messages": [
                        AIMessage(
                            content="请提供"
                            + "和".join(missing)
                            + "，我再继续查询；这些信息不会由我猜测。"
                        )
                    ],
                    "jump_to": "end",
                }
            if len(route.intents) > 1 or route.conditional:
                permitted = allowed_actions(route)
                proposed = await model.with_structured_output(
                    Plan, method="function_calling"
                ).ainvoke(
                    [
                        SystemMessage(content=PLANNER_PROMPT),
                        HumanMessage(
                            content=query
                            + "\nRouter："
                            + route.model_dump_json()
                            + "\nallowed_actions："
                            + ",".join(sorted(permitted))
                        ),
                    ]
                )
                try:
                    plan = validate_plan(Plan.model_validate(proposed), route)
                except ValueError as exc:
                    logger.warning(
                        "Planner output rejected error_type=%s reason=%s",
                        type(exc).__name__,
                        exc,
                    )
                    trace_event("planner", status="rejected", error_type=type(exc).__name__)
                    if permitted <= {"search_policy", "get_order_status"} and len(permitted) == 1:
                        plan = simple_plan(route)
                    else:
                        trace_event("router", result=safe_route(route), missing_fields=[])
                        return {
                            "route": route.model_dump(mode="json"),
                            "plan": {},
                            "task_trace": [],
                            "messages": [
                                AIMessage(
                                    content="暂时无法安全安排这些操作，请分别说明需要查询或办理的事项。"
                                )
                            ],
                            "jump_to": "end",
                        }
            else:
                plan = simple_plan(route)
        except Exception as exc:
            logger.exception("Customer support routing failed error_type=%s", type(exc).__name__)
            raise CustomerSupportModelError() from exc
        trace_event("router", result=safe_route(route), missing_fields=[])
        trace_event(
            "planner",
            steps=plan.model_dump(mode="json")["steps"],
            invoked=len(route.intents) > 1 or route.conditional,
        )
        return {
            "route": route.model_dump(mode="json"),
            "plan": plan.model_dump(mode="json"),
            "task_trace": [],
        }

    @before_model(state_schema=RoutedState)
    def record_tasks(state, runtime):
        if not state.get("plan"):
            return None
        _, trace = next_task(Plan.model_validate(state["plan"]), state["messages"])
        return {"task_trace": trace}

    @wrap_model_call
    async def execute_planned_step(request, handler):
        state = request.state or {}
        if not state.get("plan"):
            return await handler(request)
        plan = Plan.model_validate(state["plan"])
        route = Route.model_validate(state["route"])
        pending, trace = next_task(plan, state.get("messages", []))
        guidance = task_guidance(route, plan, trace)
        if pending is None:
            guidance += "任务已执行或受阻。请仅汇总真实结果与失败，不要再调用工具。"
            return await handler(
                request.override(
                    tools=[], system_message=SystemMessage(content=SYSTEM_PROMPT + "\n" + guidance)
                )
            )
        selected = [tool for tool in request.tools if getattr(tool, "name", None) == pending.action]
        if not selected:
            raise RuntimeError("Planned tool is not available")
        return await handler(
            request.override(
                tools=selected,
                tool_choice=pending.action,
                system_message=SystemMessage(content=SYSTEM_PROMPT + "\n" + guidance),
            )
        )

    return [route_request, record_tasks, execute_planned_step]


@wrap_model_call
async def assemble_model_context(request, handler):
    """Limit the model view; the checkpoint keeps the full message history."""
    budget = TokenBudget(
        total=settings.CONTEXT_TOKEN_BUDGET,
        system=settings.CONTEXT_SYSTEM_BUDGET,
        history=settings.CONTEXT_HISTORY_BUDGET,
        memory=settings.CONTEXT_MEMORY_BUDGET,
        rag=settings.CONTEXT_RAG_BUDGET,
        tools=settings.CONTEXT_TOOLS_BUDGET,
    )
    config = get_config()
    metadata = config.get("metadata") or {}
    memory = dict(metadata.get("memory_context") or {})
    compactor = get_compactor()
    scoped = config.get("configurable") or {}
    if compactor and scoped.get("user_id") and scoped.get("thread_id"):
        summary, _ = await compactor.maybe_compact(
            owner=str(scoped["user_id"]),
            thread=str(scoped["thread_id"]),
            messages=request.messages,
            system=request.system_message,
            total_budget=budget.total,
            model=request.model,
        )
        if summary:
            memory["compaction"] = summary
    if settings.CONTEXT_COMPACTION_ENABLED:
        record = None
        if compactor and scoped.get("user_id") and scoped.get("thread_id"):
            session = await compactor.store.session(str(scoped["user_id"]), str(scoped["thread_id"]))
            record = session.get("compaction")
        view = CompactedContextAssembler(
            budget,
            CandidateBudget(
                summary=settings.CONTEXT_HISTORY_SUMMARY_BUDGET,
                long_term=settings.CONTEXT_LONG_TERM_BUDGET,
                recent_turns=settings.CONTEXT_RECENT_TURNS,
            ),
        ).assemble(
            messages=request.messages,
            system=request.system_message,
            state=request.state or {},
            memory=memory,
            compaction_record=record,
            model=request.model,
        )
        messages, system_message = view.messages, view.system
        before = count_tokens(
            request.messages + ([request.system_message] if request.system_message else []),
            request.model,
        )
        after = count_tokens(messages + ([system_message] if system_message else []), request.model)
        available = int(view.metrics.get("summary_facts_available", 0))
        selected = int(view.metrics.get("summary_facts_selected", 0))
        injection_rate = selected / available if available else 0.0
        logger.info(
            "Context replacement before_tokens=%d after_tokens=%d "
            "summary_injected=%s summary_fact_injection_rate=%.3f reason=%s",
            before, after, view.metrics.get("summary_injected"), injection_rate,
            view.metrics.get("reason"),
        )
    else:
        messages, system_message = ContextManager(budget).assemble(
            messages=request.messages,
            system=request.system_message,
            state=request.state or {},
            memory=memory,
            model=request.model,
        )
    return await handler(request.override(messages=messages, system_message=system_message))


def build_customer_support_graph(
    model: BaseChatModel,
    *,
    provider: str = "qwen",
    force_routing: bool = True,
    enable_router: bool = False,
    tools: list[BaseTool] | None = None,
) -> CompiledStateGraph:
    """Build the tool-calling graph; injecting the model keeps it testable."""
    return create_agent(
        model=model,
        tools=CUSTOMER_SUPPORT_TOOLS if tools is None else tools,
        system_prompt=SYSTEM_PROMPT,
        middleware=[
            log_agent_start,
            *(routing_middleware(model) if enable_router else []),
            assemble_model_context,
            log_model_call,
            *([deterministic_tool_routing] if force_routing else []),
            HumanInTheLoopMiddleware(
                interrupt_on={
                    "create_support_ticket": {
                        "allowed_decisions": ["approve", "reject"],
                        "description": "创建客服工单属于写入操作，需要用户明确确认。",
                    }
                }
            ),
            log_tool_call,
            log_agent_end,
        ],
        name=f"customer-support-{provider}",
    )


class CustomerSupportAgent(LazyLoadingAgent):
    """Load a real provider; configuration and connection failures never downgrade."""

    def _qwen_is_configured(self) -> bool:
        return bool(
            settings.DASHSCOPE_API_KEY and settings.DASHSCOPE_BASE_URL and settings.DASHSCOPE_MODEL
        )

    async def _check_ollama(self) -> None:
        """Fail startup clearly if the selected local model is unreachable or absent."""
        url = settings.OLLAMA_BASE_URL.rstrip("/") + "/api/tags"
        try:
            async with httpx.AsyncClient(timeout=settings.OLLAMA_CONNECT_TIMEOUT) as client:
                response = await client.get(url)
                response.raise_for_status()
                names = {item.get("name") for item in response.json().get("models", [])}
        except (httpx.HTTPError, ValueError, KeyError, TypeError, AttributeError) as exc:
            logger.error("Ollama startup check failed error_type=%s", type(exc).__name__)
            raise RuntimeError("Ollama is unavailable at OLLAMA_BASE_URL") from exc
        if settings.OLLAMA_MODEL not in names:
            raise RuntimeError(f"Ollama model {settings.OLLAMA_MODEL} is not installed")

    async def load(self) -> None:
        # A failed reload must not leave a previously loaded graph available.
        self._loaded = False
        self._graph = None
        mode = settings.CUSTOMER_SUPPORT_MODE.lower()
        if mode not in {"llm", "deepseek", "qwen", "ollama"}:
            raise ValueError("CUSTOMER_SUPPORT_MODE must be llm, deepseek, qwen, or ollama")
        if mode == "qwen" and not self._qwen_is_configured():
            raise ValueError("Qwen mode requires all DASHSCOPE settings")

        selected = DeepseekModelName.DEEPSEEK_CHAT if mode == "deepseek" else settings.DEFAULT_MODEL
        if mode == "ollama" or (mode == "llm" and selected in OllamaModelName):
            await self._check_ollama()
            model: BaseChatModel = ChatOllama(
                model=settings.OLLAMA_MODEL,
                base_url=settings.OLLAMA_BASE_URL,
                temperature=0,
                reasoning=False,
                client_kwargs={"timeout": settings.OLLAMA_REQUEST_TIMEOUT},
            )
            self._graph = build_customer_support_graph(
                model,
                provider="ollama",
                force_routing=False,
                enable_router=True,
                tools=await load_business_mcp_tools(),
            )
            logger.info("Customer support provider=ollama model=%s", settings.OLLAMA_MODEL)
        elif mode == "qwen":
            model = ChatOpenAI(
                api_key=settings.DASHSCOPE_API_KEY,
                base_url=settings.DASHSCOPE_BASE_URL,
                model=settings.DASHSCOPE_MODEL,
                temperature=0,
                streaming=True,
                timeout=60,
                max_retries=2,
                extra_body={"enable_thinking": False},
            )
            self._graph = build_customer_support_graph(
                model, enable_router=True, tools=await load_business_mcp_tools()
            )
            logger.info("Customer support provider=qwen model=%s", settings.DASHSCOPE_MODEL)
        else:
            if selected is None or selected in FakeModelName:
                raise ValueError(
                    "Customer support requires a real DEFAULT_MODEL; fake is not allowed"
                )
            if selected not in settings.AVAILABLE_MODELS:
                raise ValueError("Selected customer support model has no configured provider")
            model = get_model(selected)
            self._graph = build_customer_support_graph(
                model,
                provider=mode,
                force_routing=False,
                enable_router=True,
                tools=await load_business_mcp_tools(),
            )
            logger.info("Customer support provider=%s model=%s", mode, selected)
        self._loaded = True


customer_support_agent = CustomerSupportAgent()
