"""Capability-based session isolation without trusting public user/thread IDs.

Clients keep a random 256-bit secret out of URLs. The secret scopes checkpoint
keys and long-term user namespaces across restarts without a new database.
This is session ownership, not an account login system.
"""

import hashlib
import json
import re
from typing import Annotated

from fastapi import Header, HTTPException


def session_identity(
    token: Annotated[str | None, Header(alias="X-Session-Token")] = None,
) -> str:
    if token is None or re.fullmatch(r"[0-9a-f]{64}", token) is None:
        raise HTTPException(status_code=401, detail="Valid session credential required")
    return hashlib.sha256(token.encode()).hexdigest()


def checkpoint_thread(identity: str, agent_id: str, thread_id: str) -> str:
    payload = json.dumps([identity, agent_id, thread_id], separators=(",", ":"))
    return "session-v1-" + hashlib.sha256(payload.encode()).hexdigest()
