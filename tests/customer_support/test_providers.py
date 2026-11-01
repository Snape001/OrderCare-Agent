"""Real runtime selection; test doubles never become a selectable provider."""

from unittest.mock import AsyncMock, Mock

import pytest
from langchain_core.messages import AIMessage, HumanMessage
from pydantic import SecretStr

import agents.customer_support_agent as module
from core import settings
from core.settings import Settings
from customer_support.errors import CustomerSupportModelError
from schema.models import DeepseekModelName, FakeModelName, OpenAIModelName


@pytest.fixture(autouse=True)
def isolated_mcp_loader(monkeypatch):
    """Provider-selection tests do not need to start the MCP subprocess."""
    monkeypatch.setattr(module, "load_business_mcp_tools", AsyncMock(return_value=[]))


@pytest.mark.parametrize("mode", ["mock", "auto", "unknown"])
def test_removed_modes_rejected_in_settings(mock_env, mode):
    with pytest.raises(ValueError, match="CUSTOMER_SUPPORT_MODE"):
        Settings(_env_file=None, CUSTOMER_SUPPORT_MODE=mode, OPENAI_API_KEY="test-only")


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["mock", "auto"])
async def test_removed_modes_rejected_at_load(monkeypatch, mode):
    monkeypatch.setattr(settings, "CUSTOMER_SUPPORT_MODE", mode)
    agent = module.CustomerSupportAgent()
    with pytest.raises(ValueError, match="CUSTOMER_SUPPORT_MODE"):
        await agent.load()
    assert not agent._loaded


def test_deepseek_requires_own_key(mock_env):
    with pytest.raises(ValueError, match="DEEPSEEK_API_KEY"):
        Settings(_env_file=None, CUSTOMER_SUPPORT_MODE="deepseek", OPENAI_API_KEY="test-only")


def test_deepseek_only_configuration(mock_env):
    config = Settings(
        _env_file=None, CUSTOMER_SUPPORT_MODE="deepseek", DEEPSEEK_API_KEY="test-only"
    )
    assert config.DEFAULT_MODEL == DeepseekModelName.DEEPSEEK_CHAT


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "mode,selected",
    [
        ("deepseek", DeepseekModelName.DEEPSEEK_CHAT),
        ("llm", OpenAIModelName.GPT_5_NANO),
    ],
)
async def test_api_provider_uses_shared_model_factory(monkeypatch, mode, selected):
    monkeypatch.setattr(settings, "CUSTOMER_SUPPORT_MODE", mode)
    monkeypatch.setattr(settings, "DEFAULT_MODEL", selected)
    monkeypatch.setattr(settings, "AVAILABLE_MODELS", {selected})
    factory = Mock(return_value=Mock())
    build = Mock(return_value=Mock())
    monkeypatch.setattr(module, "get_model", factory)
    monkeypatch.setattr(module, "build_customer_support_graph", build)
    agent = module.CustomerSupportAgent()
    await agent.load()
    factory.assert_called_once_with(selected)
    assert agent._loaded
    assert build.call_args.kwargs["force_routing"] is False


@pytest.mark.asyncio
async def test_qwen_still_uses_tool_calling_graph(monkeypatch):
    monkeypatch.setattr(settings, "CUSTOMER_SUPPORT_MODE", "qwen")
    monkeypatch.setattr(settings, "DASHSCOPE_API_KEY", SecretStr("test-only"))
    monkeypatch.setattr(settings, "DASHSCOPE_BASE_URL", "https://example.com/v1")
    monkeypatch.setattr(settings, "DASHSCOPE_MODEL", "test-qwen")
    build = Mock(return_value=Mock())
    monkeypatch.setattr(module, "build_customer_support_graph", build)
    agent = module.CustomerSupportAgent()
    await agent.load()
    assert build.call_args.args[0].model_name == "test-qwen"
    assert agent._loaded


@pytest.mark.asyncio
async def test_fake_cannot_be_selected_for_customer_support(monkeypatch):
    monkeypatch.setattr(settings, "CUSTOMER_SUPPORT_MODE", "llm")
    monkeypatch.setattr(settings, "DEFAULT_MODEL", FakeModelName.FAKE)
    agent = module.CustomerSupportAgent()
    with pytest.raises(ValueError, match="real DEFAULT_MODEL"):
        await agent.load()
    assert not agent._loaded


@pytest.mark.asyncio
async def test_failed_reload_discards_old_graph(monkeypatch):
    monkeypatch.setattr(settings, "CUSTOMER_SUPPORT_MODE", "llm")
    monkeypatch.setattr(settings, "DEFAULT_MODEL", OpenAIModelName.GPT_5_NANO)
    monkeypatch.setattr(settings, "AVAILABLE_MODELS", {OpenAIModelName.GPT_5_NANO})
    monkeypatch.setattr(module, "get_model", Mock(side_effect=ConnectionError("unavailable")))
    agent = module.CustomerSupportAgent()
    agent._loaded = True
    agent._graph = Mock()
    with pytest.raises(ConnectionError):
        await agent.load()
    assert agent._graph is None
    with pytest.raises(RuntimeError, match="not loaded"):
        agent.get_graph()


@pytest.mark.asyncio
async def test_model_connection_failure_propagates_without_answer():
    from langchain_core.language_models import FakeMessagesListChatModel

    class UnreachableModel(FakeMessagesListChatModel):
        def bind_tools(self, tools, **kwargs):
            return self

        async def _agenerate(self, *args, **kwargs):
            raise ConnectionError("private-provider-details")

    graph = module.build_customer_support_graph(
        UnreachableModel(responses=[AIMessage(content="must not be returned")]),
        force_routing=False,
    )
    with pytest.raises(CustomerSupportModelError, match="No fallback") as error:
        await graph.ainvoke({"messages": [HumanMessage(content="你好")]})
    assert "private-provider-details" not in str(error.value)


def test_llm_provider_environment_switch(mock_env):
    local = Settings(_env_file=None, LLM_PROVIDER="ollama", OLLAMA_MODEL="qwen3:4b")
    cloud = Settings(_env_file=None, LLM_PROVIDER="deepseek", DEEPSEEK_API_KEY="test-only")
    assert local.CUSTOMER_SUPPORT_MODE == "ollama"
    assert cloud.CUSTOMER_SUPPORT_MODE == "deepseek"
    assert cloud.DEEPSEEK_MODEL == "deepseek-flash"


def test_deepseek_configuration_validation(mock_env):
    with pytest.raises(ValueError, match="DEEPSEEK_BASE_URL"):
        Settings(
            _env_file=None,
            LLM_PROVIDER="deepseek",
            DEEPSEEK_API_KEY="test-only",
            DEEPSEEK_BASE_URL="http://invalid",
        )
    with pytest.raises(ValueError, match="DEEPSEEK_TIMEOUT"):
        Settings(
            _env_file=None,
            LLM_PROVIDER="deepseek",
            DEEPSEEK_API_KEY="test-only",
            DEEPSEEK_TIMEOUT=0,
        )
