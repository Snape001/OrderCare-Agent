"""Explicit approval parsing shared by mock and model-backed write flows."""


def is_explicit_approval(message: str) -> bool:
    return message.strip().rstrip("。！!").strip() in {"确认", "同意", "批准", "执行"}
