"""Three-stage service-restart check against an isolated test Redis URL.

Run --write, restart the selected test Redis service, run --verify, --cleanup.
The marker is local temporary test metadata, not a memory or checkpoint file.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path
from uuid import uuid4

from langchain_core.messages import AIMessage, AnyMessage, HumanMessage

from memory.compaction import AutomaticCompactor
from memory.layers import LayeredMemory


async def run(stage: str, marker: Path) -> None:
    url = os.getenv("ORDERCARE_TEST_REDIS_URL")
    if not url or "127.0.0.1" not in url:
        raise ValueError("An explicit loopback ORDERCARE_TEST_REDIS_URL is required")
    store = LayeredMemory(url, marker.parent / "restart-check.db", ttl=120)
    try:
        await store.setup()
        if stage == "write":
            owner = f"restart-{uuid4().hex}"
            thread = f"thread-{uuid4().hex}"
            messages: list[AnyMessage] = [
                HumanMessage(content="订单 ORD1001 需要先确认退货资格，不要直接建工单"),
                AIMessage(content="已记录"),
                HumanMessage(content="请保留限制"),
                AIMessage(content="收到"),
                HumanMessage(content="下一步呢？"),
            ]
            summary, metrics = await AutomaticCompactor(store).maybe_compact(
                owner=owner, thread=thread, messages=messages,
                system=None, total_budget=100,
            )
            if summary is None or not metrics["triggered"]:
                raise AssertionError("Compaction write did not occur")
            record = (await store.session(owner, thread))["compaction"]
            marker.parent.mkdir(parents=True, exist_ok=True)
            marker.write_text(json.dumps({"owner": owner, "thread": thread,
                                          "cursor": record["cursor"]}), encoding="utf-8")
            print(json.dumps({"stage": stage, "stored": True, "cursor": record["cursor"]}))
        else:
            saved = json.loads(marker.read_text(encoding="utf-8"))
            if stage == "verify":
                record = (await store.session(saved["owner"], saved["thread"]))["compaction"]
                if record["cursor"] != saved["cursor"]:
                    raise AssertionError("Cursor changed after service restart")
                if "ORD1001" not in record["summary"]["entities"]:
                    raise AssertionError("Summary was lost after service restart")
                print(json.dumps({"stage": stage, "persisted": True,
                                  "cursor_unchanged": True}))
            elif stage == "cleanup":
                await store.delete_session(saved["owner"], saved["thread"])
                marker.unlink()
                print(json.dumps({"stage": stage, "deleted": True}))
    finally:
        await store.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("stage", choices=("write", "verify", "cleanup"))
    parser.add_argument("--marker", type=Path, default=Path(".tmp/redis-restart-marker.json"))
    args = parser.parse_args()
    asyncio.run(run(args.stage, args.marker))


if __name__ == "__main__":
    main()
