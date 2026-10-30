from unittest.mock import AsyncMock

import pytest
from langchain_core.messages import HumanMessage

from agents import knowledge_base_agent as kb


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", [False, True])
async def test_new_retrieval_clears_previous_evidence(monkeypatch, failure):
    retriever = AsyncMock()
    retriever.ainvoke.return_value = []
    if failure:
        retriever.ainvoke.side_effect = RuntimeError("unavailable")
    monkeypatch.setattr(kb, "get_kb_retriever", lambda: retriever)
    state = {"messages": [HumanMessage(content="new question")], "kb_documents": "old evidence"}
    update = await kb.retrieve_documents(state, {})
    assert update["retrieved_documents"] == []
    assert update["kb_documents"] == ""
    state.update(update)
    prepared = await kb.prepare_augmented_prompt(state, {})
    assert prepared["kb_documents"] == ""


@pytest.mark.asyncio
async def test_no_user_message_clears_evidence():
    result = await kb.retrieve_documents({"messages": [], "kb_documents": "old"}, {})
    assert result["kb_documents"] == ""
    assert result["retrieved_documents"] == []
