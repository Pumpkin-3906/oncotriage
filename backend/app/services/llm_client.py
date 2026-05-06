"""LLM 客户端抽象 —— 解耦 Extractor 与具体 SDK。

为什么要这层抽象（DESIGN.md §5.① 感知环节的演进）：
- 业务逻辑 (prompt 构造 / JSON 解析 / 字典校验) 由 LLMExtractor 负责
- 网络协议 (Anthropic Messages API / OpenAI Chat Completions) 由 LLMClient 实现
- 异常翻译 (anthropic.APIError / openai.APIError → LLMClientError) 在 client 层完成

新增 provider 只需实现 `complete(system, user) -> str`；
切换 provider 不需要改 extractor、不需要改测试。
"""
from __future__ import annotations

from typing import Protocol

from app.config import settings


class LLMClientError(Exception):
    """provider 无关的 LLM 调用失败 —— 由 LLMExtractor 翻译成 LLMExtractionError"""
    pass


class LLMClient(Protocol):
    """LLM 客户端的最小契约。

    实现类把 system_prompt + user_message 发到底层 provider，返回纯文本响应。
    所有底层 SDK 异常必须翻译成 LLMClientError；返回值不允许为空字符串或 None。
    """

    model: str  # 用于审计：assessment.extraction_model_version 写这个值

    def complete(self, system_prompt: str, user_message: str) -> str: ...


class AnthropicLLMClient:
    """Anthropic Messages API 实现 —— base_url 可指向兼容端点（如 DeepSeek 的 Anthropic-compat）"""

    def __init__(
        self,
        api_key: str,
        model: str,
        max_tokens: int,
        temperature: float,
        timeout: float,
        base_url: str | None = None,
    ) -> None:
        import anthropic  # 延迟导入：让只用 OpenAI 的部署不强依赖 anthropic SDK
        if not api_key:
            raise LLMClientError("anthropic_api_key is empty; set ANTHROPIC_API_KEY")
        self._anthropic = anthropic
        kwargs: dict = {"api_key": api_key}
        if base_url:
            kwargs["base_url"] = base_url
        self.client = anthropic.Anthropic(**kwargs)
        self.model = model
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.timeout = timeout

    def complete(self, system_prompt: str, user_message: str) -> str:
        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                temperature=self.temperature,
                timeout=self.timeout,
                system=system_prompt,
                messages=[{"role": "user", "content": user_message}],
            )
        except self._anthropic.APIError as e:
            raise LLMClientError(f"Anthropic API call failed: {e}") from e

        # 响应可能含多种 content block：text / thinking / tool_use 等
        # （reasoning model 与 DeepSeek Anthropic-compat 端点都会返 thinking 块）
        # 只取第一个 text 块；没有则视为失败。
        text_blocks = [b for b in (response.content or []) if getattr(b, "type", None) == "text"]
        if not text_blocks:
            raise LLMClientError(
                f"Anthropic response has no text block "
                f"(stop_reason={getattr(response, 'stop_reason', None)!r}, "
                f"got types={[getattr(b, 'type', '?') for b in (response.content or [])]})"
            )
        text = text_blocks[0].text
        if not text:
            raise LLMClientError("Anthropic returned empty text")
        return text


class OpenAILLMClient:
    """OpenAI Chat Completions 兼容实现 —— 适配 OpenAI 官方 / DeepSeek / Qwen / OpenRouter / vLLM / ollama 等"""

    def __init__(
        self,
        api_key: str,
        base_url: str,
        model: str,
        max_tokens: int,
        temperature: float,
        timeout: float,
    ) -> None:
        import openai  # 延迟导入
        if not api_key:
            raise LLMClientError("openai_api_key is empty; set OPENAI_API_KEY")
        self._openai = openai
        self.client = openai.OpenAI(api_key=api_key, base_url=base_url, timeout=timeout)
        self.model = model
        self.max_tokens = max_tokens
        self.temperature = temperature

    def complete(self, system_prompt: str, user_message: str) -> str:
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                max_tokens=self.max_tokens,
                temperature=self.temperature,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message},
                ],
            )
        except self._openai.APIError as e:
            raise LLMClientError(f"OpenAI API call failed: {e}") from e

        if not response.choices:
            raise LLMClientError("OpenAI response has no choices")
        text = response.choices[0].message.content
        if not text:
            raise LLMClientError("OpenAI returned empty content")
        return text


def build_default_llm_client() -> LLMClient:
    """根据 settings.llm_provider 构造默认 client。

    业务代码默认通过 LLMExtractor() 间接调用此函数；测试可绕过它直接注入 FakeLLMClient。
    """
    provider = (settings.llm_provider or "").strip().lower()
    if provider == "openai":
        return OpenAILLMClient(
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url,
            model=settings.openai_model,
            max_tokens=settings.llm_max_tokens,
            temperature=settings.llm_temperature,
            timeout=settings.llm_timeout_seconds,
        )
    if provider in ("", "anthropic"):
        return AnthropicLLMClient(
            api_key=settings.anthropic_api_key,
            model=settings.anthropic_model,
            max_tokens=settings.llm_max_tokens,
            temperature=settings.llm_temperature,
            timeout=settings.llm_timeout_seconds,
            base_url=settings.anthropic_base_url or None,
        )
    raise LLMClientError(f"Unknown llm_provider: {settings.llm_provider!r}")
