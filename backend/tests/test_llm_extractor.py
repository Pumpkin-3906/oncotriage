"""LLMExtractor 单测 —— 用 FakeLLMClient 注入桩响应。

extractor 只关心 LLMClient 协议（complete(system, user) -> str），
所以这一层测试不再 mock 任何 SDK 内部。
provider 级别的接线测试见 test_llm_client.py。

覆盖：
1. happy: 高烧 + 化疗描述 → 合法 ParsedSymptoms
2. markdown 围栏兼容
3. LLM 返回乱码（无 JSON）→ LLMExtractionError
4. LLM 返回字典外 symptom_id → LLMExtractionError
5. JSON 不符合 ParsedSymptoms schema → LLMExtractionError
6. LLMClient 抛 LLMClientError（API 异常）→ LLMExtractionError
7. 空字典上游 bug → 立即报错不打 LLM
"""
import json

import pytest

from app.rules.seed_dictionary import SYMPTOMS
from app.services.llm_client import LLMClientError
from app.services.llm_extractor import LLMExtractionError, LLMExtractor


class FakeLLMClient:
    """测试桩 —— 实现 LLMClient 协议，返回预置文本或抛指定异常。

    用法:
        FakeLLMClient(response='{...}')          # complete() 返回该字符串
        FakeLLMClient(error=LLMClientError(...))  # complete() 抛该异常
    """

    model = "fake-model-v1"

    def __init__(self, response: str | None = None, error: Exception | None = None) -> None:
        self.response = response
        self.error = error
        self.calls: list[tuple[str, str]] = []  # 记录 (system, user) 用于断言

    def complete(self, system_prompt: str, user_message: str) -> str:
        self.calls.append((system_prompt, user_message))
        if self.error is not None:
            raise self.error
        assert self.response is not None, "FakeLLMClient: response or error must be set"
        return self.response


def _make_extractor(response: str | None = None, error: Exception | None = None) -> tuple[LLMExtractor, FakeLLMClient]:
    fake = FakeLLMClient(response=response, error=error)
    return LLMExtractor(client=fake), fake


def test_extract_happy_path_fever_with_chemo():
    """高烧 + 化疗描述 → 返回 ParsedSymptoms，含 fever 与 days_since_chemo"""
    fake_json = json.dumps({
        "symptoms": [
            {
                "symptom_id": "fever",
                "numeric_value": 38.5,
                "numeric_unit": "C",
                "categorical_value": None,
                "ctcae_grade": None,
                "duration_hours": 4.0,
                "interferes_with_adl": None,
            }
        ],
        "context": {"days_since_chemo": 3},
        "confidence": 0.92,
    })
    extractor, fake = _make_extractor(response=fake_json)

    result = extractor.extract(
        "昨天打完化疗第三天，今天下午开始发烧 38.5 度，浑身发冷",
        SYMPTOMS,
    )

    # client 被调用了一次，system prompt 含字典 grounding
    assert len(fake.calls) == 1
    system_prompt, user_message = fake.calls[0]
    assert "fever" in system_prompt           # 字典 ID 嵌入了
    assert "发烧" in system_prompt             # 别名嵌入了
    assert "化疗第三天" in user_message         # 用户原文原样透传

    # 抽取结果正确
    assert len(result.symptoms) == 1
    assert result.symptoms[0].symptom_id == "fever"
    assert result.symptoms[0].numeric_value == 38.5
    assert result.context["days_since_chemo"] == 3
    assert result.confidence is not None and result.confidence >= 0.8


def test_extract_handles_markdown_code_fence():
    """LLM 偶尔会在 JSON 外裹 ```json ... ```，应该兼容"""
    fake_json = """```json
    {
      "symptoms": [{"symptom_id": "nausea", "categorical_value": "mild"}],
      "context": {},
      "confidence": 0.7
    }
    ```"""
    extractor, _ = _make_extractor(response=fake_json)

    result = extractor.extract("有点想吐", SYMPTOMS)

    assert result.symptoms[0].symptom_id == "nausea"
    assert result.symptoms[0].categorical_value == "mild"


def test_extract_raises_on_garbage_response():
    """LLM 返回 'I don't know...' 这种没有 JSON 的乱码 → LLMExtractionError"""
    extractor, _ = _make_extractor(response="I don't know what you're talking about.")

    with pytest.raises(LLMExtractionError, match="No JSON"):
        extractor.extract("一些奇怪的输入", SYMPTOMS)


def test_extract_raises_on_unknown_symptom_id():
    """LLM 返回字典外的 symptom_id (如 'diabetes') → LLMExtractionError"""
    fake_json = json.dumps({
        "symptoms": [{"symptom_id": "diabetes", "categorical_value": "moderate"}],
        "context": {},
        "confidence": 0.8,
    })
    extractor, _ = _make_extractor(response=fake_json)

    with pytest.raises(LLMExtractionError, match="not in dictionary"):
        extractor.extract("我有糖尿病", SYMPTOMS)


def test_extract_raises_on_schema_mismatch():
    """JSON 合法但不符合 ParsedSymptoms schema → LLMExtractionError"""
    # confidence > 1.0 违反 Field(ge=0, le=1) 约束
    fake_json = json.dumps({
        "symptoms": [{"symptom_id": "fever", "numeric_value": 38.0}],
        "context": {},
        "confidence": 5.0,
    })
    extractor, _ = _make_extractor(response=fake_json)

    with pytest.raises(LLMExtractionError, match="ParsedSymptoms schema"):
        extractor.extract("发烧 38 度", SYMPTOMS)


def test_extract_translates_client_error():
    """LLMClient 抛 LLMClientError（API 超时/限流/5xx）→ 包装成 LLMExtractionError"""
    extractor, _ = _make_extractor(error=LLMClientError("Anthropic API call failed: timeout"))

    with pytest.raises(LLMExtractionError, match="Anthropic API call failed"):
        extractor.extract("发烧", SYMPTOMS)


def test_extract_raises_on_empty_dictionary():
    """空字典是上游 bug，应立即报错而不是去调 LLM"""
    extractor, fake = _make_extractor(response="{}")

    with pytest.raises(LLMExtractionError, match="dictionary_snapshot is empty"):
        extractor.extract("发烧", [])

    # 没调 LLM —— 早失败、早便宜
    assert fake.calls == []


def test_extractor_exposes_client_model():
    """extractor.model 透传 client.model，供审计字段 extraction_model_version 使用"""
    extractor, _ = _make_extractor(response="{}")
    assert extractor.model == "fake-model-v1"
