"""Internal signature for the local MCP ticket-write boundary."""

from __future__ import annotations

import hashlib
import hmac
import json


def ticket_token(secret: str, arguments: dict[str, str]) -> str:
    payload = json.dumps(arguments, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
