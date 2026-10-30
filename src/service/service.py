import inspect
import json
import logging
import secrets
import warnings
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Annotated, Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from fastapi.routing import APIRoute
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from langchain_core._api import LangChainBetaWarning
from langchain_core.messages import AIMessage, AIMessageChunk, AnyMessage, HumanMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from langfuse import Langfuse  # type: ignore[import-untyped]
from langfuse.langchain import (
    CallbackHandler,  # type: ignore[import-untyped]
)
from langgraph.types import Command, Interrupt
from langsmith import Client as LangsmithClient
from langsmith import uuid7

from agents import DEFAULT_AGENT, AgentGraph, get_agent, get_all_agent_info, load_agent
from core import settings
from customer_support.confirmation import is_explicit_approval
from memory import initialize_database, initialize_store
from schema import (
    ChatHistory,
    ChatHistoryInput,
    ChatMessage,
    Feedback,
    FeedbackResponse,
    ServiceMetadata,
    StreamInput,
    UserInput,
)
from service.access import checkpoint_thread, session_identity
from service.presentation import approval_message, public_customer_message
from service.utils import (
    convert_message_content_to_string,
    langchain_to_chat_message,
    remove_tool_calls,
)

warnings.filterwarnings("ignore", category=LangChainBetaWarning)
logger = logging.getLogger(__name__)


def _private_customer_mode(agent_id: str) -> bool:
    return agent_id == DEFAULT_AGENT and settings.CUSTOMER_SUPPORT_MODE == "ollama"


def _is_hitl_request(value: Any) -> bool:
    return (
        isinstance(value, dict)
        and isinstance(value.get("action_requests"), list)
        and bool(value["action_requests"])
    )


def _format_interrupt(value: Any) -> str:
    """Turn a structured tool approval request into a user-facing message."""
    if not _is_hitl_request(value):
        return str(value)

    actions = value["action_requests"]
    descriptions = [
        f"- `{action['name']}`：{json.dumps(action['args'], ensure_ascii=False)}"
        for action in actions
    ]
    return (
        "即将执行以下写操作：\n\n"
        + "\n".join(descriptions)
        + "\n\n请回复“确认”执行，或回复“取消”。"
    )


def _hitl_resume_value(message: str, value: Any) -> Any:
    """Map a chat confirmation to LangChain's structured HITL decision."""
    if not _is_hitl_request(value):
        return message

    approved = is_explicit_approval(message)
    decisions = []
    for _ in value["action_requests"]:
        if approved:
            decisions.append({"type": "approve"})
        else:
            decisions.append(
                {
                    "type": "reject",
                    "message": "用户未明确确认或已取消，本次写操作未执行。",
                }
            )
    return {"decisions": decisions}


def custom_generate_unique_id(route: APIRoute) -> str:
    """Generate idiomatic operation IDs for OpenAPI client generation."""
    return route.name


def verify_bearer(
    http_auth: Annotated[
        HTTPAuthorizationCredentials | None,
        Depends(HTTPBearer(description="Please provide AUTH_SECRET api key.", auto_error=False)),
    ],
) -> None:
    if not settings.AUTH_SECRET:
        return
    auth_secret = settings.AUTH_SECRET.get_secret_value()
    if not http_auth or not secrets.compare_digest(http_auth.credentials, auth_secret):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)


def verify_database_admin(
    http_auth: Annotated[
        HTTPAuthorizationCredentials | None, Depends(HTTPBearer(auto_error=False))
    ],
) -> None:
    if not settings.DATABASE_ADMIN_SECRET:
        raise HTTPException(status_code=503, detail="Database browser is disabled")
    if not http_auth:
        raise HTTPException(status_code=401, detail="Administrator credential required")
    if not secrets.compare_digest(
        http_auth.credentials, settings.DATABASE_ADMIN_SECRET.get_secret_value()
    ):
        raise HTTPException(status_code=403, detail="Administrator access required")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    Configurable lifespan that initializes the appropriate database checkpointer, store,
    and agents with async loading - for example for starting up MCP clients.
    """
    try:
        # Initialize both checkpointer (for short-term memory) and store (for long-term memory)
        async with initialize_database() as saver, initialize_store() as store:
            # Set up both components
            if hasattr(saver, "setup"):  # ignore: union-attr
                await saver.setup()
            # Only setup store for Postgres as InMemoryStore doesn't need setup
            if hasattr(store, "setup"):  # ignore: union-attr
                await store.setup()

            if not settings.AUTH_SECRET:
                logger.warning(
                    "AUTH_SECRET is not configured — application bearer authentication is disabled. "
                    "Set AUTH_SECRET in your environment to enable bearer token authentication."
                )

            # Configure agents with both memory components and async loading
            agents = get_all_agent_info()
            app.state.unavailable_agents = set()
            for a in agents:
                try:
                    await load_agent(a.key)
                    agent = get_agent(a.key)
                    agent.checkpointer = saver
                    agent.store = store
                    logger.info(f"Agent loaded: {a.key}")
                except Exception:
                    logger.error("Failed to load agent %s", a.key)
                    app.state.unavailable_agents.add(a.key)
                    if a.key == DEFAULT_AGENT:
                        raise RuntimeError("Default agent failed to initialize") from None
            yield
    except Exception:
        logger.error("Database/store/agent initialization failed")
        raise


app = FastAPI(lifespan=lifespan, generate_unique_id_function=custom_generate_unique_id)
router = APIRouter(dependencies=[Depends(verify_bearer)])


def available_agent(agent_id: str) -> AgentGraph:
    if agent_id in getattr(app.state, "unavailable_agents", set()):
        raise HTTPException(status_code=503, detail="Agent is unavailable")
    try:
        return get_agent(agent_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Unknown agent") from None
    except RuntimeError:
        raise HTTPException(status_code=503, detail="Agent is unavailable") from None


def scope_input[InputT: UserInput](user_input: InputT, identity: str, agent_id: str) -> InputT:
    return user_input.model_copy(
        update={
            "thread_id": checkpoint_thread(
                identity, agent_id, user_input.thread_id or str(uuid4())
            ),
            "user_id": identity,
        }
    )


@router.get("/info")
async def info() -> ServiceMetadata:
    models = list(settings.AVAILABLE_MODELS)
    models.sort()
    return ServiceMetadata(
        agents=[
            a
            for a in get_all_agent_info()
            if a.key not in getattr(app.state, "unavailable_agents", set())
        ],
        models=models,
        default_agent=DEFAULT_AGENT,
        default_model=settings.DEFAULT_MODEL,
    )


async def _handle_input(user_input: UserInput, agent: AgentGraph) -> tuple[dict[str, Any], UUID]:
    """
    Parse user input and handle any required interrupt resumption.
    Returns kwargs for agent invocation and the run_id.
    """
    run_id = uuid7()
    thread_id = user_input.thread_id or str(uuid4())
    user_id = user_input.user_id or str(uuid4())

    configurable = {"thread_id": thread_id, "user_id": user_id}
    if user_input.model is not None:
        configurable["model"] = user_input.model

    callbacks: list[Any] = []
    if settings.LANGFUSE_TRACING:
        # Initialize Langfuse CallbackHandler for Langchain (tracing)
        langfuse_handler = CallbackHandler()

        callbacks.append(langfuse_handler)

    if user_input.agent_config:
        # Check for reserved keys (including 'model' even if not in configurable)
        reserved_keys = {
            "thread_id",
            "user_id",
            "model",
            "checkpoint_id",
            "checkpoint_ns",
            "checkpoint_map",
        }
        if any(key.startswith("__") for key in user_input.agent_config):
            raise HTTPException(status_code=422, detail="Internal configuration keys are reserved")
        if overlap := reserved_keys & user_input.agent_config.keys():
            raise HTTPException(
                status_code=422,
                detail=f"agent_config contains reserved keys: {overlap}",
            )
        configurable.update(user_input.agent_config)

    config = RunnableConfig(
        configurable=configurable,
        run_id=run_id,
        callbacks=callbacks,
    )

    # Check for interrupts that need to be resumed
    state = await agent.aget_state(config=config)
    interrupted_tasks = [
        task for task in state.tasks if hasattr(task, "interrupts") and task.interrupts
    ]

    input: Command | dict[str, Any]
    if interrupted_tasks:
        # assume user input is response to resume agent execution from interrupt
        interrupt_value = interrupted_tasks[0].interrupts[0].value
        input = Command(resume=_hitl_resume_value(user_input.message, interrupt_value))
    else:
        input = {"messages": [HumanMessage(content=user_input.message)]}

    kwargs = {
        "input": input,
        "config": config,
    }

    return kwargs, run_id


@router.post("/{agent_id}/invoke", operation_id="invoke_with_agent_id")
@router.post("/invoke")
async def invoke(
    user_input: UserInput,
    identity: Annotated[str, Depends(session_identity)],
    agent_id: str = DEFAULT_AGENT,
) -> ChatMessage:
    """
    Invoke an agent with user input to retrieve a final response.

    If agent_id is not provided, the default agent will be used.
    Use thread_id to persist and continue a multi-turn conversation. run_id kwarg
    is also attached to messages for recording feedback.
    Use user_id to persist and continue a conversation across multiple threads.
    """
    # NOTE: Currently this only returns the last message or interrupt.
    # In the case of an agent outputting multiple AIMessages (such as the background step
    # in interrupt-agent, or a tool step in research-assistant), it's omitted. Arguably,
    # you'd want to include it. You could update the API to return a list of ChatMessages
    # in that case.
    agent: AgentGraph = available_agent(agent_id)
    user_input = scope_input(user_input, identity, agent_id)
    kwargs, run_id = await _handle_input(user_input, agent)

    try:
        response_events: list[tuple[str, Any]] = await agent.ainvoke(**kwargs, stream_mode=["updates", "values"])  # type: ignore # fmt: skip
        output = None
        for response_type, response in response_events:
            if response_type == "updates" and "__interrupt__" in response:
                output = (
                    approval_message()
                    if _private_customer_mode(agent_id)
                    else langchain_to_chat_message(
                        AIMessage(content=_format_interrupt(response["__interrupt__"][0].value))
                    )
                )
                break
        if output is None:
            for response_type, response in reversed(response_events):
                if response_type == "values":
                    output = (
                        public_customer_message(response["messages"][-1])
                        if _private_customer_mode(agent_id)
                        else langchain_to_chat_message(response["messages"][-1])
                    )
                    break
        if output is None:
            event_types = [response_type for response_type, _ in response_events]
            raise ValueError(f"No final values or interrupt event found: {event_types}")

        output.run_id = str(run_id)
        return output
    except Exception as e:
        logger.error("Agent invocation failed (%s)", type(e).__name__)
        raise HTTPException(status_code=500, detail="Unexpected error")


async def message_generator(
    user_input: StreamInput, agent_id: str = DEFAULT_AGENT
) -> AsyncGenerator[str, None]:
    """
    Generate a stream of messages from the agent.

    This is the workhorse method for the /stream endpoint.
    """
    agent: AgentGraph = available_agent(agent_id)
    kwargs, run_id = await _handle_input(user_input, agent)

    if _private_customer_mode(agent_id):
        # Keep model chunks and tool messages inside the graph. A completed AI
        # message is the first safe point to publish a customer-support answer.
        try:
            final: ChatMessage | None = None
            interrupted = False
            async for item in agent.astream(**kwargs, stream_mode=["updates"], subgraphs=True):
                if not isinstance(item, tuple):
                    continue
                mode, update = (item[1], item[2]) if len(item) == 3 else item
                if mode != "updates" or not isinstance(update, dict):
                    continue
                if "__interrupt__" in update:
                    interrupted = True
                    continue
                for node_update in update.values():
                    if not isinstance(node_update, dict):
                        continue
                    for message in node_update.get("messages", []):
                        public = public_customer_message(message)
                        if public is not None and public.type == "ai":
                            final = public
            output = approval_message() if interrupted else final
            if output is not None:
                output.run_id = str(run_id)
                yield f"data: {json.dumps({'type': 'message', 'content': output.model_dump()})}\n\n"
        except Exception as error:
            logger.error("Customer support stream failed (%s)", type(error).__name__)
            yield f"data: {json.dumps({'type': 'error', 'content': 'Internal server error'})}\n\n"
        finally:
            yield "data: [DONE]\n\n"
        return

    try:
        # Process streamed events from the graph and yield messages over the SSE stream.
        async for stream_event in agent.astream(
            **kwargs, stream_mode=["updates", "messages", "custom"], subgraphs=True
        ):
            if not isinstance(stream_event, tuple):
                continue
            # Handle different stream event structures based on subgraphs
            if len(stream_event) == 3:
                # With subgraphs=True: (node_path, stream_mode, event)
                _, stream_mode, event = stream_event
            else:
                # Without subgraphs: (stream_mode, event)
                stream_mode, event = stream_event
            new_messages = []
            if stream_mode == "updates":
                for node, updates in event.items():
                    # A simple approach to handle agent interrupts.
                    # In a more sophisticated implementation, we could add
                    # some structured ChatMessage type to return the interrupt value.
                    if node == "__interrupt__":
                        interrupt: Interrupt
                        for interrupt in updates:
                            new_messages.append(
                                AIMessage(content=_format_interrupt(interrupt.value))
                            )
                        continue
                    updates = updates or {}
                    update_messages = updates.get("messages", [])
                    # special cases for using langgraph-supervisor library
                    if "supervisor" in node or "sub-agent" in node:
                        # the only tools that come from the actual agent are the handoff and handback tools
                        if isinstance(update_messages[-1], ToolMessage):
                            if "sub-agent" in node and len(update_messages) > 1:
                                # If this is a sub-agent, we want to keep the last 2 messages - the handback tool, and it's result
                                update_messages = update_messages[-2:]
                            else:
                                # If this is a supervisor, we want to keep the last message only - the handoff result. The tool comes from the 'agent' node.
                                update_messages = [update_messages[-1]]
                        else:
                            update_messages = []
                    new_messages.extend(update_messages)

            if stream_mode == "custom":
                new_messages = [event]

            # LangGraph streaming may emit tuples: (field_name, field_value)
            # e.g. ('content', <str>), ('tool_calls', [ToolCall,...]), ('additional_kwargs', {...}), etc.
            # We accumulate only supported fields into `parts` and skip unsupported metadata.
            # More info at: https://langchain-ai.github.io/langgraph/cloud/how-tos/stream_messages/
            processed_messages = []
            current_message: dict[str, Any] = {}
            for message in new_messages:
                if isinstance(message, tuple):
                    key, value = message
                    # Store parts in temporary dict
                    current_message[key] = value
                else:
                    # Add complete message if we have one in progress
                    if current_message:
                        processed_messages.append(_create_ai_message(current_message))
                        current_message = {}
                    processed_messages.append(message)

            # Add any remaining message parts
            if current_message:
                processed_messages.append(_create_ai_message(current_message))

            for message in processed_messages:
                try:
                    chat_message = langchain_to_chat_message(message)
                    chat_message.run_id = str(run_id)
                except Exception as e:
                    logger.error("Message parsing failed (%s)", type(e).__name__)
                    yield f"data: {json.dumps({'type': 'error', 'content': 'Unexpected error'})}\n\n"
                    continue
                # LangGraph re-sends the input message, which feels weird, so drop it
                if chat_message.type == "human" and chat_message.content == user_input.message:
                    continue
                yield f"data: {json.dumps({'type': 'message', 'content': chat_message.model_dump()})}\n\n"

            if stream_mode == "messages":
                if not user_input.stream_tokens:
                    continue
                msg, metadata = event
                if "skip_stream" in metadata.get("tags", []):
                    continue
                # For some reason, astream("messages") causes non-LLM nodes to send extra messages.
                # Drop them.
                if not isinstance(msg, AIMessageChunk):
                    continue
                content = remove_tool_calls(msg.content)
                if content:
                    # Empty content in the context of OpenAI usually means
                    # that the model is asking for a tool to be invoked.
                    # So we only print non-empty content.
                    yield f"data: {json.dumps({'type': 'token', 'content': convert_message_content_to_string(content)})}\n\n"
    except Exception as e:
        logger.error("Message generation failed (%s)", type(e).__name__)
        yield f"data: {json.dumps({'type': 'error', 'content': 'Internal server error'})}\n\n"
    finally:
        yield "data: [DONE]\n\n"


def _create_ai_message(parts: dict) -> AIMessage:
    sig = inspect.signature(AIMessage)
    valid_keys = set(sig.parameters)
    filtered = {k: v for k, v in parts.items() if k in valid_keys}
    return AIMessage(**filtered)


def _sse_response_example() -> dict[int | str, Any]:
    return {
        status.HTTP_200_OK: {
            "description": "Server Sent Event Response",
            "content": {
                "text/event-stream": {
                    "example": "data: {'type': 'token', 'content': 'Hello'}\n\ndata: {'type': 'token', 'content': ' World'}\n\ndata: [DONE]\n\n",
                    "schema": {"type": "string"},
                }
            },
        }
    }


@router.post(
    "/{agent_id}/stream",
    response_class=StreamingResponse,
    responses=_sse_response_example(),
    operation_id="stream_with_agent_id",
)
@router.post("/stream", response_class=StreamingResponse, responses=_sse_response_example())
async def stream(
    user_input: StreamInput,
    identity: Annotated[str, Depends(session_identity)],
    agent_id: str = DEFAULT_AGENT,
) -> StreamingResponse:
    """
    Stream an agent's response to a user input, including intermediate messages and tokens.

    If agent_id is not provided, the default agent will be used.
    Use thread_id to persist and continue a multi-turn conversation. run_id kwarg
    is also attached to all messages for recording feedback.
    Use user_id to persist and continue a conversation across multiple threads.

    Set `stream_tokens=false` to return intermediate messages but not token-by-token.
    """
    available_agent(agent_id)
    scoped = scope_input(user_input, identity, agent_id)
    # Validate reserved configuration before sending HTTP 200 for the SSE stream.
    if any(
        key in {"thread_id", "user_id", "model", "checkpoint_id", "checkpoint_ns", "checkpoint_map"}
        or key.startswith("__")
        for key in user_input.agent_config
    ):
        raise HTTPException(status_code=422, detail="Reserved agent configuration")
    return StreamingResponse(
        message_generator(scoped, agent_id),
        media_type="text/event-stream",
    )


@router.post("/feedback")
async def feedback(feedback: Feedback) -> FeedbackResponse:
    """
    Record feedback for a run to LangSmith.

    This is a simple wrapper for the LangSmith create_feedback API, so the
    credentials can be stored and managed in the service rather than the client.
    See: https://api.smith.langchain.com/redoc#tag/feedback/operation/create_feedback_api_v1_feedback_post
    """
    client = LangsmithClient()
    kwargs = feedback.kwargs or {}
    client.create_feedback(
        run_id=feedback.run_id,
        key=feedback.key,
        score=feedback.score,
        **kwargs,
    )
    return FeedbackResponse()


@router.post("/history")
async def history(
    input: ChatHistoryInput,
    identity: Annotated[str, Depends(session_identity)],
) -> ChatHistory:
    """
    Get chat history.
    """
    agent: AgentGraph = available_agent(input.agent_id)
    try:
        state_snapshot = await agent.aget_state(
            config=RunnableConfig(
                configurable={
                    "thread_id": checkpoint_thread(identity, input.agent_id, input.thread_id),
                    "user_id": identity,
                }
            )
        )
        messages: list[AnyMessage] = state_snapshot.values.get("messages", [])
        if _private_customer_mode(input.agent_id):
            chat_messages = [
                public for m in messages if (public := public_customer_message(m)) is not None
            ]
        else:
            chat_messages = [langchain_to_chat_message(m) for m in messages]
        return ChatHistory(messages=chat_messages)
    except Exception as e:
        logger.error("History retrieval failed (%s)", type(e).__name__)
        raise HTTPException(status_code=500, detail="Unexpected error")


@app.get("/health")
async def health_check():
    """Health check endpoint."""

    health_status = {"status": "ok"}

    if settings.LANGFUSE_TRACING:
        try:
            langfuse = Langfuse()
            health_status["langfuse"] = "connected" if langfuse.auth_check() else "disconnected"
        except Exception as e:
            logger.error("Tracing connection failed (%s)", type(e).__name__)
            health_status["langfuse"] = "disconnected"

    return health_status


@app.get("/ready")
def readiness_check():
    """Readiness probe that also verifies the configured business database."""
    import os

    if os.getenv("BUSINESS_DATABASE_TYPE", "sqlite").lower() != "mysql":
        return {"status": "ready", "business_database": "sqlite"}
    try:
        from customer_support.mysql_store import database_healthcheck

        return database_healthcheck()
    except Exception as error:
        logger.error("Business database readiness check failed (%s)", type(error).__name__)
        raise HTTPException(status_code=503, detail="Business database is not ready") from error


@app.get("/database/tables", dependencies=[Depends(verify_database_admin)])
def database_tables():
    """List tables for the local read-only database learning page."""
    from customer_support.mysql_store import list_database_tables

    return {"tables": list_database_tables()}


@app.get("/database/tables/{table}", dependencies=[Depends(verify_database_admin)])
def database_table_rows(
    table: str,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    order_alias: str | None = None,
):
    """Return a read-only page; arbitrary SQL and write operations are not exposed."""
    from customer_support.mysql_store import browse_database_table

    try:
        return browse_database_table(table, limit, offset, order_alias)
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


app.include_router(router)
