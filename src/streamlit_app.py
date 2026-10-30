import asyncio
import logging
import math
import os
import time
import urllib.parse
import uuid
from collections.abc import AsyncGenerator, Awaitable, Callable
from contextlib import suppress
from typing import Any

import streamlit as st
from dotenv import load_dotenv
from pydantic import ValidationError

from client import AgentClient, AgentClientError
from schema import ChatHistory, ChatMessage
from schema.presentation import public_answer
from schema.task_data import TaskData, TaskDataStatus
from voice import VoiceManager

# A Streamlit app for interacting with the langgraph agent via a simple chat interface.
# The app has three main functions which are all run async:

# - main() - sets up the streamlit app and high level structure
# - draw_messages() - draws a set of chat messages - either replaying existing messages
#   or streaming new ones.
# - handle_feedback() - Draws a feedback widget and records feedback from the user.

# The app heavily uses AgentClient to interact with the agent's FastAPI endpoints.


APP_TITLE = "OrderCare-Agent｜电商客服助手"
APP_ICON = "🧰"
USER_ID_COOKIE = "user_id"
REQUEST_TIMEOUT_ENV = "STREAMLIT_REQUEST_TIMEOUT_SECONDS"
DEFAULT_REQUEST_TIMEOUT_SECONDS = 300.0
logger = logging.getLogger(__name__)


def _request_timeout_seconds() -> float:
    """Use a finite, positive overall deadline for a chat request."""
    try:
        timeout = float(os.getenv(REQUEST_TIMEOUT_ENV, str(DEFAULT_REQUEST_TIMEOUT_SECONDS)))
    except ValueError:
        return DEFAULT_REQUEST_TIMEOUT_SECONDS
    return timeout if math.isfinite(timeout) and timeout > 0 else DEFAULT_REQUEST_TIMEOUT_SECONDS


def _mark_request_in_flight() -> None:
    """The chat widget callback runs before this script renders again."""
    if not st.session_state.get("request_in_flight", False):
        st.session_state.request_in_flight = True
        st.session_state.request_submitted = True


async def _await_with_wait_status[T](
    request: Awaitable[T],
    placeholder: Any,
    *,
    timeout_seconds: float,
    clock: Callable[[], float] = time.monotonic,
) -> T:
    """Refresh the waiting label while the existing async request is pending."""
    started_at = clock()
    placeholder.info("思考中……已用时 0 秒", icon="⏳")
    request_task = asyncio.create_task(request)
    shown_seconds = 0
    try:
        while not request_task.done():
            remaining = timeout_seconds - (clock() - started_at)
            if remaining <= 0:
                raise TimeoutError("Agent request timed out")
            await asyncio.wait({request_task}, timeout=min(1.0, remaining))
            if not request_task.done():
                elapsed_seconds = int(clock() - started_at)
                if elapsed_seconds > shown_seconds:
                    placeholder.info(f"思考中……已用时 {elapsed_seconds} 秒", icon="⏳")
                    shown_seconds = elapsed_seconds
        return await request_task
    finally:
        if not request_task.done():
            request_task.cancel()
            with suppress(asyncio.CancelledError):
                await request_task
        placeholder.empty()


def get_or_create_user_id() -> str:
    """Get the user ID from session state or URL parameters, or create a new one if it doesn't exist."""
    # Check if user_id exists in session state
    if USER_ID_COOKIE in st.session_state:
        return st.session_state[USER_ID_COOKIE]

    # Generate a new user_id if not found
    user_id = str(uuid.uuid4())

    # Store in session state for this session
    st.session_state[USER_ID_COOKIE] = user_id

    return user_id


async def main() -> None:
    st.set_page_config(
        page_title=APP_TITLE,
        page_icon=APP_ICON,
        menu_items={},
    )

    # A script rerun cancels the in-process request. Release its UI lock and
    # report the interruption instead of leaving the input disabled.
    if st.session_state.get("request_processing", False):
        st.session_state.request_processing = False
        st.session_state.request_in_flight = False
        st.session_state.request_submitted = False
        st.session_state.request_error = "请求已中断，请重新发送。"

    # Hide the streamlit upper-right chrome
    st.html(
        """
        <style>
        [data-testid="stStatusWidget"] {
                visibility: hidden;
                height: 0%;
                position: fixed;
            }
        </style>
        """,
    )
    if st.get_option("client.toolbarMode") != "minimal":
        st.set_option("client.toolbarMode", "minimal")
        await asyncio.sleep(0.1)
        st.rerun()

    # Get or create user ID
    user_id = get_or_create_user_id()

    if "agent_client" not in st.session_state:
        load_dotenv()
        agent_url = os.getenv("AGENT_URL")
        if not agent_url:
            host = os.getenv("HOST", "0.0.0.0")
            port = os.getenv("PORT", 8080)
            agent_url = f"http://{host}:{port}"
        try:
            with st.spinner("Connecting to agent service..."):
                st.session_state.agent_client = AgentClient(base_url=agent_url)
        except AgentClientError as e:
            st.error(f"Error connecting to agent service at {agent_url}: {e}")
            st.markdown("The service might be booting up. Try again in a few seconds.")
            st.stop()
    agent_client: AgentClient = st.session_state.agent_client

    # Initialize voice manager (once per session)
    if "voice_manager" not in st.session_state:
        st.session_state.voice_manager = VoiceManager.from_env()
    voice = st.session_state.voice_manager

    if "thread_id" not in st.session_state:
        thread_id = st.query_params.get("thread_id")
        if not thread_id:
            thread_id = str(uuid.uuid4())
            messages = []
        else:
            try:
                messages: ChatHistory = agent_client.get_history(thread_id=thread_id).messages
            except AgentClientError:
                st.error("No message history found for this Thread ID.")
                messages = []
        st.session_state.messages = messages
        st.session_state.thread_id = thread_id

    # Config options
    with st.sidebar:
        st.header(f"{APP_ICON} {APP_TITLE}")

        ""
        "Full toolkit for running an AI agent service built with LangGraph, FastAPI and Streamlit"
        ""

        if st.button(
            ":material/chat: New Chat",
            use_container_width=True,
            disabled=st.session_state.get("request_in_flight", False),
        ):
            st.session_state.messages = []
            st.session_state.thread_id = str(uuid.uuid4())
            # Clear saved audio when starting new chat
            if "last_audio" in st.session_state:
                del st.session_state.last_audio
            st.rerun()

        with st.popover(":material/settings: Settings", use_container_width=True):
            model_idx = agent_client.info.models.index(agent_client.info.default_model)
            model = st.selectbox("LLM to use", options=agent_client.info.models, index=model_idx)
            agent_list = [a.key for a in agent_client.info.agents]
            agent_idx = agent_list.index(agent_client.info.default_agent)
            agent_client.agent = st.selectbox(
                "Agent to use",
                options=agent_list,
                index=agent_idx,
            )
            use_streaming = st.toggle("Stream results", value=True)
            # Audio toggle with callback: clears cached audio when toggled off
            enable_audio = st.toggle(
                "Enable audio generation",
                value=True,
                disabled=not voice or not voice.tts,
                help="Configure VOICE_TTS_PROVIDER in .env to enable"
                if not voice or not voice.tts
                else None,
                on_change=lambda: (
                    st.session_state.pop("last_audio", None)
                    if not st.session_state.get("enable_audio", True)
                    else None
                ),
                key="enable_audio",
            )

            # Display user ID (for debugging or user information)
            st.text_input("User ID (read-only)", value=user_id, disabled=True)

        @st.dialog("Architecture")
        def architecture_dialog() -> None:
            st.image(
                "https://raw.githubusercontent.com/Snape001/OrderCare-Agent/main/media/agent_architecture.png"
            )
            "[在 GitHub 查看原图](https://github.com/Snape001/OrderCare-Agent/blob/main/media/agent_architecture.png)"
            st.caption(
                "App hosted on [Streamlit Cloud](https://share.streamlit.io/) with FastAPI service running in [Azure](https://learn.microsoft.com/en-us/azure/app-service/)"
            )

        if st.button(":material/schema: Architecture", use_container_width=True):
            architecture_dialog()

        with st.popover(":material/policy: Privacy", use_container_width=True):
            st.write(
                "Prompts, responses and feedback in this app are anonymously recorded and saved to LangSmith for product evaluation and improvement purposes only."
            )

        @st.dialog("Share/resume chat")
        def share_chat_dialog() -> None:
            # Use Streamlit's public request context. The former implementation
            # reached into private session internals, which changed in Streamlit
            # 1.58 and caused an AttributeError when opening this dialog.
            try:
                current_url = str(st.context.url)
            except Exception:
                current_url = os.getenv("STREAMLIT_PUBLIC_URL", "http://127.0.0.1:8501")
            parsed_url = urllib.parse.urlsplit(current_url)
            st_base_url = urllib.parse.urlunsplit(
                (parsed_url.scheme, parsed_url.netloc, parsed_url.path, "", "")
            )
            # if it's not localhost, switch to https by default
            is_local = parsed_url.hostname in {"localhost", "127.0.0.1", "0.0.0.0"}
            if not st_base_url.startswith("https") and not is_local:
                st_base_url = st_base_url.replace("http", "https")
            # A public thread ID is not an access credential. Never share session secrets.
            chat_url = f"{st_base_url}?thread_id={st.session_state.thread_id}"
            st.markdown(f"**Chat URL:**\n```text\n{chat_url}\n```")
            st.info(
                "此链接仅标记会话，不能授权他人读取。恢复需要原客户端会话凭证；刷新后可能需要新建聊天。"
            )

        if st.button(":material/upload: Share/resume chat", use_container_width=True):
            share_chat_dialog()

        "[OrderCare-Agent 源码](https://github.com/Snape001/OrderCare-Agent)"
        st.caption("OrderCare-Agent · 许可证与原始版权声明见仓库 LICENSE")

    # Draw existing messages
    messages: list[ChatMessage] = st.session_state.messages

    if len(messages) == 0:
        match agent_client.agent:
            case "customer-support":
                WELCOME = """你好！我是电商智能客服演示助手。
                我可以查询政策、订单和退款资格，并在你确认后创建客服工单。
                你可以先试试：查询订单 ORD1001，手机号后四位 8821"""
            case "chatbot":
                WELCOME = "Hello! I'm a simple chatbot. Ask me anything!"
            case "interrupt-agent":
                WELCOME = "Hello! I'm an interrupt agent. Tell me your birthday and I will predict your personality!"
            case "research-assistant":
                WELCOME = "Hello! I'm an AI-powered research assistant with web search and a calculator. Ask me anything!"
            case "rag-assistant":
                WELCOME = """Hello! I'm an AI-powered Company Policy & HR assistant with access to AcmeTech's Employee Handbook.
                I can help you find information about benefits, remote work, time-off policies, company values, and more. Ask me anything!"""
            case _:
                WELCOME = "Hello! I'm an AI agent. Ask me anything!"

        with st.chat_message("ai"):
            st.write(WELCOME)

    # draw_messages() expects an async iterator over messages
    async def amessage_iter() -> AsyncGenerator[ChatMessage, None]:
        for m in messages:
            yield m

    await draw_messages(amessage_iter())

    # Render saved audio for the last AI message (if it exists)
    # This ensures audio persists across st.rerun() calls
    if (
        voice
        and enable_audio
        and "last_audio" in st.session_state
        and st.session_state.last_message
        and len(messages) > 0
        and messages[-1].type == "ai"
    ):
        with st.session_state.last_message:
            audio_data = st.session_state.last_audio
            st.audio(audio_data["data"], format=audio_data["format"])

    if request_error := st.session_state.pop("request_error", None):
        st.error(request_error)

    # Generate new message if the user provided new input
    # Use voice manager if available, otherwise fall back to regular input
    # REQUIRED: Set VOICE_STT_PROVIDER, VOICE_TTS_PROVIDER, OPENAI_API_KEY
    # in app .env (NOT service .env) to enable voice features.
    if voice:
        user_input = voice.get_chat_input(
            disabled=st.session_state.get("request_in_flight", False),
            on_submit=_mark_request_in_flight,
            key="chat_prompt",
        )
    else:
        user_input = st.chat_input(
            disabled=st.session_state.get("request_in_flight", False),
            on_submit=_mark_request_in_flight,
            key="chat_prompt",
        )

    if user_input:
        if st.session_state.get("request_processing", False) or not st.session_state.get(
            "request_submitted", False
        ):
            return
        st.session_state.request_submitted = False
        st.session_state.request_in_flight = True
        st.session_state.request_processing = True
        messages.append(ChatMessage(type="human", content=user_input))
        st.chat_message("human").write(user_input)
        status_placeholder = st.empty()
        timeout_seconds = _request_timeout_seconds()
        try:
            if use_streaming:
                stream = agent_client.astream(
                    message=user_input,
                    model=model,
                    thread_id=st.session_state.thread_id,
                    user_id=user_id,
                )
                await _await_with_wait_status(
                    draw_messages(stream, is_new=True),
                    status_placeholder,
                    timeout_seconds=timeout_seconds,
                )
                # Generate TTS audio for streaming response
                # Note: draw_messages() stores the final message in st.session_state.messages
                # and the container reference in st.session_state.last_message
                if voice and enable_audio and st.session_state.messages:
                    last_msg = st.session_state.messages[-1]
                    # Only generate audio for AI responses with content
                    if last_msg.type == "ai" and last_msg.content:
                        # Use audio_only=True since text was already streamed by draw_messages()
                        voice.render_message(
                            last_msg.content,
                            container=st.session_state.last_message,
                            audio_only=True,
                        )
            else:
                response = await _await_with_wait_status(
                    agent_client.ainvoke(
                        message=user_input,
                        model=model,
                        thread_id=st.session_state.thread_id,
                        user_id=user_id,
                    ),
                    status_placeholder,
                    timeout_seconds=timeout_seconds,
                )
                if agent_client.agent == "customer-support":
                    answer = public_answer(response.content)
                    if answer is None:
                        raise AgentClientError("No public answer received")
                    response = response.model_copy(update={"content": answer})
                messages.append(response)
                # Render AI response with optional voice
                with st.chat_message("ai"):
                    if voice and enable_audio:
                        voice.render_message(response.content)
                    else:
                        st.write(response.content)
        except TimeoutError:
            st.session_state.request_error = "请求超时，请稍后重试。"
        except AgentClientError:
            st.session_state.request_error = "请求失败，请检查服务连接后重试。"
        except Exception as exc:
            logger.error("Chat request failed: %s", type(exc).__name__)
            st.session_state.request_error = "请求处理失败，请稍后重试。"
        except BaseException:
            st.session_state.request_error = "请求已中断，请重新发送。"
            raise
        finally:
            st.session_state.request_processing = False
            st.session_state.request_in_flight = False
        st.rerun()  # Re-enable input and clear stale containers
    elif st.session_state.pop("request_submitted", False):
        # For example, voice transcription failed after the submit callback.
        st.session_state.request_in_flight = False
        st.session_state.request_error = "未收到有效消息，请重试。"
        st.rerun()

    # If messages have been generated, show feedback widget
    if len(messages) > 0 and st.session_state.last_message:
        with st.session_state.last_message:
            await handle_feedback()


async def draw_messages(
    messages_agen: AsyncGenerator[ChatMessage | str, None],
    is_new: bool = False,
) -> None:
    """
    Draws a set of chat messages - either replaying existing messages
    or streaming new ones.

    This function has additional logic to handle streaming tokens and tool calls.
    - Use a placeholder container to render streaming tokens as they arrive.
    - Use a status container to render tool calls. Track the tool inputs and outputs
      and update the status container accordingly.

    The function also needs to track the last message container in session state
    since later messages can draw to the same container. This is also used for
    drawing the feedback widget in the latest chat message.

    Args:
        messages_aiter: An async iterator over messages to draw.
        is_new: Whether the messages are new or not.
    """

    if st.session_state.agent_client.agent == "customer-support":
        await _draw_customer_messages(messages_agen, is_new=is_new)
        return

    # Keep track of the last message container
    last_message_type = None
    st.session_state.last_message = None

    # Placeholder for intermediate streaming tokens
    streaming_content = ""
    streaming_placeholder = None

    # A tool call is normally followed immediately by a ToolMessage. HITL is the
    # important exception: the graph emits an interrupt/approval message first,
    # and the ToolMessage arrives only after the user resumes the run. Keep that
    # non-tool message here so the outer loop can render it normally.
    pending_msg: ChatMessage | str | None = None

    # Iterate over the messages and draw them
    while True:
        if pending_msg is not None:
            msg = pending_msg
            pending_msg = None
        else:
            msg = await anext(messages_agen, None)
        if msg is None:
            break

        # str message represents an intermediate token being streamed
        if isinstance(msg, str):
            # If placeholder is empty, this is the first token of a new message
            # being streamed. We need to do setup.
            if not streaming_placeholder:
                if last_message_type != "ai":
                    last_message_type = "ai"
                    st.session_state.last_message = st.chat_message("ai")
                with st.session_state.last_message:
                    streaming_placeholder = st.empty()

            streaming_content += msg
            streaming_placeholder.write(streaming_content)
            continue
        if not isinstance(msg, ChatMessage):
            st.error(f"Unexpected message type: {type(msg)}")
            st.write(msg)
            st.stop()

        match msg.type:
            # A message from the user, the easiest case
            case "human":
                last_message_type = "human"
                st.chat_message("human").write(msg.content)

            # A message from the agent is the most complex case, since we need to
            # handle streaming tokens and tool calls.
            case "ai":
                # If we're rendering new messages, store the message in session state
                if is_new:
                    st.session_state.messages.append(msg)

                # If the last message type was not AI, create a new chat message
                if last_message_type != "ai":
                    last_message_type = "ai"
                    st.session_state.last_message = st.chat_message("ai")

                with st.session_state.last_message:
                    # If the message has content, write it out.
                    # Reset the streaming variables to prepare for the next message.
                    if msg.content:
                        if streaming_placeholder:
                            streaming_placeholder.write(msg.content)
                            streaming_content = ""
                            streaming_placeholder = None
                        else:
                            st.write(msg.content)

                    if msg.tool_calls:
                        # Create a status container for each tool call and store the
                        # status container by ID to ensure results are mapped to the
                        # correct status container.
                        call_results = {}
                        for tool_call in msg.tool_calls:
                            # Use different labels for transfer vs regular tool calls
                            if "transfer_to" in tool_call["name"]:
                                label = f"""💼 Sub Agent: {tool_call["name"]}"""
                            else:
                                label = f"""🛠️ Tool Call: {tool_call["name"]}"""

                            status = st.status(
                                label,
                                state="running" if is_new else "complete",
                            )
                            call_results[tool_call["id"]] = status

                        # Expect one ToolMessage for each tool call.
                        for tool_call in msg.tool_calls:
                            if "transfer_to" in tool_call["name"]:
                                status = call_results[tool_call["id"]]
                                status.update(expanded=True)
                                await handle_sub_agent_msgs(messages_agen, status, is_new)
                                break

                            # Only non-transfer tool calls reach this point
                            status = call_results[tool_call["id"]]
                            status.write("Input:")
                            status.write(tool_call["args"])
                            tool_result = await anext(messages_agen, None)

                            if tool_result is None or tool_result.type != "tool":
                                status.write("等待用户确认，请在下方输入“确认”或“取消”。")
                                status.update(
                                    label=f"⏸️ Waiting for approval: {tool_call['name']}",
                                    state="complete",
                                )
                                # The interrupt prompt belongs to the normal message
                                # stream; do not swallow it while looking for a tool
                                # result.
                                pending_msg = tool_result
                                break

                            # Record the message if it's new, and update the correct
                            # status container with the result
                            if is_new:
                                st.session_state.messages.append(tool_result)
                            if tool_result.tool_call_id:
                                status = call_results[tool_result.tool_call_id]
                            status.write("Output:")
                            status.write(tool_result.content)
                            status.update(state="complete")

            # After an HITL resume, LangGraph may emit the ToolMessage without
            # repeating the earlier AI tool-call message in this HTTP stream.
            # Render it as a standalone result instead of treating it as invalid.
            case "tool":
                if is_new:
                    st.session_state.messages.append(msg)

                if last_message_type != "ai":
                    last_message_type = "ai"
                    st.session_state.last_message = st.chat_message("ai")

                with st.session_state.last_message:
                    status = st.status("🛠️ Tool result", state="complete")
                    status.write("Output:")
                    status.write(msg.content)

            case "custom":
                # CustomData example used by the bg-task-agent
                # See:
                # - src/agents/utils.py CustomData
                # - src/agents/bg_task_agent/task.py
                try:
                    task_data: TaskData = TaskData.model_validate(msg.custom_data)
                except ValidationError:
                    st.error("Unexpected CustomData message received from agent")
                    st.write(msg.custom_data)
                    st.stop()

                if is_new:
                    st.session_state.messages.append(msg)

                if last_message_type != "task":
                    last_message_type = "task"
                    st.session_state.last_message = st.chat_message(
                        name="task", avatar=":material/manufacturing:"
                    )
                    with st.session_state.last_message:
                        status = TaskDataStatus()

                status.add_and_draw_task_data(task_data)

            # In case of an unexpected message type, log an error and stop
            case _:
                st.error(f"Unexpected ChatMessage type: {msg.type}")
                st.write(msg)
                st.stop()


async def _draw_customer_messages(
    messages_agen: AsyncGenerator[ChatMessage | str, None],
    *,
    is_new: bool,
) -> None:
    """Show only completed customer replies; keep tool traffic out of the chat."""
    st.session_state.last_message = None
    pending_answer: ChatMessage | None = None

    def show_pending_answer() -> None:
        nonlocal pending_answer
        if pending_answer is None:
            return
        if is_new:
            st.session_state.messages.append(pending_answer)
        container = st.chat_message("ai")
        container.write(pending_answer.content)
        st.session_state.last_message = container
        pending_answer = None

    async for msg in messages_agen:
        if isinstance(msg, str) or not isinstance(msg, ChatMessage):
            continue
        if msg.type == "human":
            show_pending_answer()
            st.chat_message("human").write(msg.content)
        elif msg.type == "ai" and not msg.tool_calls:
            answer = public_answer(msg.content)
            if answer:
                pending_answer = msg.model_copy(update={"content": answer})
    show_pending_answer()


async def handle_feedback() -> None:
    """Draws a feedback widget and records feedback from the user."""

    # Keep track of last feedback sent to avoid sending duplicates
    if "last_feedback" not in st.session_state:
        st.session_state.last_feedback = (None, None)

    latest_run_id = st.session_state.messages[-1].run_id
    feedback = st.feedback("stars", key=latest_run_id)

    # If the feedback value or run ID has changed, send a new feedback record
    if feedback is not None and (latest_run_id, feedback) != st.session_state.last_feedback:
        # Normalize the feedback value (an index) to a score between 0 and 1
        normalized_score = (feedback + 1) / 5.0

        agent_client: AgentClient = st.session_state.agent_client
        try:
            await agent_client.acreate_feedback(
                run_id=latest_run_id,
                key="human-feedback-stars",
                score=normalized_score,
                kwargs={"comment": "In-line human feedback"},
            )
        except AgentClientError as e:
            st.error(f"Error recording feedback: {e}")
            st.stop()
        st.session_state.last_feedback = (latest_run_id, feedback)
        st.toast("Feedback recorded", icon=":material/reviews:")


async def handle_sub_agent_msgs(messages_agen, status, is_new):
    """
    This function segregates agent output into a status container.
    It handles all messages after the initial tool call message
    until it reaches the final AI message.

    Enhanced to support nested multi-agent hierarchies with handoff back messages.

    Args:
        messages_agen: Async generator of messages
        status: the status container for the current agent
        is_new: Whether messages are new or replayed
    """
    nested_popovers = {}

    # looking for the transfer Success tool call message
    first_msg = await anext(messages_agen)
    if is_new:
        st.session_state.messages.append(first_msg)

    # Continue reading until we get an explicit handoff back
    while True:
        # Read next message
        sub_msg = await anext(messages_agen)

        # this should only happen is skip_stream flag is removed
        # if isinstance(sub_msg, str):
        #     continue

        if is_new:
            st.session_state.messages.append(sub_msg)

        # Handle tool results with nested popovers
        if sub_msg.type == "tool" and sub_msg.tool_call_id in nested_popovers:
            popover = nested_popovers[sub_msg.tool_call_id]
            popover.write("**Output:**")
            popover.write(sub_msg.content)
            continue

        # Handle transfer_back_to tool calls - these indicate a sub-agent is returning control
        if (
            hasattr(sub_msg, "tool_calls")
            and sub_msg.tool_calls
            and any("transfer_back_to" in tc.get("name", "") for tc in sub_msg.tool_calls)
        ):
            # Process transfer_back_to tool calls
            for tc in sub_msg.tool_calls:
                if "transfer_back_to" in tc.get("name", ""):
                    # Read the corresponding tool result
                    transfer_result = await anext(messages_agen)
                    if is_new:
                        st.session_state.messages.append(transfer_result)

            # After processing transfer back, we're done with this agent
            if status:
                status.update(state="complete")
            break

        # Display content and tool calls in the same nested status
        if status:
            if sub_msg.content:
                status.write(sub_msg.content)

            if hasattr(sub_msg, "tool_calls") and sub_msg.tool_calls:
                for tc in sub_msg.tool_calls:
                    # Check if this is a nested transfer/delegate
                    if "transfer_to" in tc["name"]:
                        # Create a nested status container for the sub-agent
                        nested_status = status.status(
                            f"""💼 Sub Agent: {tc["name"]}""",
                            state="running" if is_new else "complete",
                            expanded=True,
                        )

                        # Recursively handle sub-agents of this sub-agent
                        await handle_sub_agent_msgs(messages_agen, nested_status, is_new)
                    else:
                        # Regular tool call - create popover
                        popover = status.popover(f"{tc['name']}", icon="🛠️")
                        popover.write(f"**Tool:** {tc['name']}")
                        popover.write("**Input:**")
                        popover.write(tc["args"])
                        # Store the popover reference using the tool call ID
                        nested_popovers[tc["id"]] = popover


if __name__ == "__main__":
    asyncio.run(main())
