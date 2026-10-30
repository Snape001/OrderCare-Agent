"""Public customer-support view of an agent run; raw graph state stays intact."""

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage

from schema import ChatMessage
from schema.presentation import ThinkingFilter, public_answer
from service.utils import langchain_to_chat_message

__all__ = ["ThinkingFilter", "public_customer_message"]


def public_customer_message(message: BaseMessage) -> ChatMessage | None:
    """Expose only human text and completed AI answers, never tool internals."""
    if isinstance(message, HumanMessage):
        return langchain_to_chat_message(message)
    if not isinstance(message, AIMessage) or message.tool_calls:
        return None
    content = langchain_to_chat_message(message).content
    answer = public_answer(content)
    return ChatMessage(type="ai", content=answer) if answer else None


def approval_message() -> ChatMessage:
    return ChatMessage(type="ai", content="创建客服工单需要确认。请回复“确认”执行，或回复“取消”。")
