"""LLMClient 实现的 SDK 接线测试 —— mock 各家 SDK 的 create() 方法。

这层测试只验证：参数透传正确 + 异常翻译正确 + 返回值解析正确。
不验证 prompt 内容（那是 extractor 的职责）。
"""
from unittest.mock import MagicMock, patch

import anthropic
import httpx
import openai
import pytest

from app.services.llm_client import (
    AnthropicLLMClient,
    LLMClientError,
    OpenAILLMClient,
    build_default_llm_client,
)


# ── Anthropic client ─────────────────────────────────────────

def _anthropic_response(text: str) -> MagicMock:
    block = MagicMock()
    block.text = text
    response = MagicMock()
    response.content = [block]
    return response


def test_anthropic_client_passes_params_and_returns_text():
    client = AnthropicLLMClient(
        api_key="sk-ant-test", model="claude-x", max_tokens=512, temperature=0.0, timeout=10
    )

    with patch.object(
        client.client.messages, "create", return_value=_anthropic_response("hello")
    ) as mock_create:
        result = client.complete("SYS", "USER")

    assert result == "hello"
    kwargs = mock_create.call_args.kwargs
    assert kwargs["model"] == "claude-x"
    assert kwargs["max_tokens"] == 512
    assert kwargs["temperature"] == 0.0
    assert kwargs["timeout"] == 10
    assert kwargs["system"] == "SYS"
    assert kwargs["messages"] == [{"role": "user", "content": "USER"}]


def test_anthropic_client_translates_api_error():
    client = AnthropicLLMClient(
        api_key="sk-ant-test", model="claude-x", max_tokens=512, temperature=0.0, timeout=10
    )
    fake_request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    api_error = anthropic.APIConnectionError(request=fake_request)

    with patch.object(client.client.messages, "create", side_effect=api_error):
        with pytest.raises(LLMClientError, match="Anthropic API call failed"):
            client.complete("SYS", "USER")


def test_anthropic_client_raises_on_empty_response():
    client = AnthropicLLMClient(
        api_key="sk-ant-test", model="claude-x", max_tokens=512, temperature=0.0, timeout=10
    )
    empty = MagicMock()
    empty.content = []

    with patch.object(client.client.messages, "create", return_value=empty):
        with pytest.raises(LLMClientError, match="no text content"):
            client.complete("SYS", "USER")


def test_anthropic_client_rejects_empty_api_key():
    with pytest.raises(LLMClientError, match="anthropic_api_key is empty"):
        AnthropicLLMClient(
            api_key="", model="claude-x", max_tokens=512, temperature=0.0, timeout=10
        )


# ── OpenAI client (covers DeepSeek/Qwen/OpenRouter/vLLM via base_url) ─────

def _openai_response(text: str | None) -> MagicMock:
    msg = MagicMock()
    msg.content = text
    choice = MagicMock()
    choice.message = msg
    response = MagicMock()
    response.choices = [choice]
    return response


def test_openai_client_passes_params_and_returns_text():
    client = OpenAILLMClient(
        api_key="sk-test",
        base_url="https://api.deepseek.com/v1",
        model="deepseek-chat",
        max_tokens=512,
        temperature=0.0,
        timeout=10,
    )

    with patch.object(
        client.client.chat.completions, "create", return_value=_openai_response("world")
    ) as mock_create:
        result = client.complete("SYS", "USER")

    assert result == "world"
    kwargs = mock_create.call_args.kwargs
    assert kwargs["model"] == "deepseek-chat"
    assert kwargs["max_tokens"] == 512
    assert kwargs["temperature"] == 0.0
    assert kwargs["messages"] == [
        {"role": "system", "content": "SYS"},
        {"role": "user", "content": "USER"},
    ]


def test_openai_client_translates_api_error():
    client = OpenAILLMClient(
        api_key="sk-test",
        base_url="https://api.openai.com/v1",
        model="gpt-4o-mini",
        max_tokens=512,
        temperature=0.0,
        timeout=10,
    )
    fake_request = httpx.Request("POST", "https://api.openai.com/v1/chat/completions")
    api_error = openai.APIConnectionError(request=fake_request)

    with patch.object(client.client.chat.completions, "create", side_effect=api_error):
        with pytest.raises(LLMClientError, match="OpenAI API call failed"):
            client.complete("SYS", "USER")


def test_openai_client_raises_on_empty_content():
    """OpenAI 偶尔会返回 message.content=None（如纯 tool_call 响应）—— 视为失败"""
    client = OpenAILLMClient(
        api_key="sk-test",
        base_url="https://api.openai.com/v1",
        model="gpt-4o-mini",
        max_tokens=512,
        temperature=0.0,
        timeout=10,
    )

    with patch.object(
        client.client.chat.completions, "create", return_value=_openai_response(None)
    ):
        with pytest.raises(LLMClientError, match="empty content"):
            client.complete("SYS", "USER")


def test_openai_client_rejects_empty_api_key():
    with pytest.raises(LLMClientError, match="openai_api_key is empty"):
        OpenAILLMClient(
            api_key="",
            base_url="https://api.openai.com/v1",
            model="gpt-4o-mini",
            max_tokens=512,
            temperature=0.0,
            timeout=10,
        )


# ── Factory ───────────────────────────────────────────────────

def test_build_default_picks_openai_when_configured(monkeypatch):
    """settings.llm_provider='openai' → 工厂返回 OpenAILLMClient"""
    from app.services import llm_client as mod
    monkeypatch.setattr(mod.settings, "llm_provider", "openai")
    monkeypatch.setattr(mod.settings, "openai_api_key", "sk-test")

    instance = build_default_llm_client()
    assert isinstance(instance, OpenAILLMClient)


def test_build_default_picks_anthropic_by_default(monkeypatch):
    """settings.llm_provider='anthropic' → 工厂返回 AnthropicLLMClient"""
    from app.services import llm_client as mod
    monkeypatch.setattr(mod.settings, "llm_provider", "anthropic")
    monkeypatch.setattr(mod.settings, "anthropic_api_key", "sk-ant-test")

    instance = build_default_llm_client()
    assert isinstance(instance, AnthropicLLMClient)


def test_build_default_rejects_unknown_provider(monkeypatch):
    from app.services import llm_client as mod
    monkeypatch.setattr(mod.settings, "llm_provider", "bedrock")

    with pytest.raises(LLMClientError, match="Unknown llm_provider"):
        build_default_llm_client()
