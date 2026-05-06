"""LLMExtractor 单测 —— 用 mock 桩掉 Anthropic API。

覆盖 4 类失败路径 + 1 个 happy path：
1. happy: 高烧 + 化疗描述 → 合法 ParsedSymptoms
2. fail: LLM 返回乱码（无 JSON）→ LLMExtractionError
3. fail: LLM 返回字典外 symptom_id → LLMExtractionError
4. fail: LLM JSON 不符合 schema → LLMExtractionError
5. fail: Anthropic API 抛异常（超时/限流）→ LLMExtractionError
"""
import json
from unittest.mock import MagicMock, patch

import anthropic
import httpx
import pytest

from app.rules.seed_dictionary import SYMPTOMS
from app.services.llm_extractor import LLMExtractionError, LLMExtractor


def _mock_response(text: str) -> MagicMock:
    """构造一个 messages.create() 的桩返回值。

    Anthropic SDK 的真实响应是 anthropic.types.Message，含 content[0].text。
    用 MagicMock 模拟即可，extractor 只读 content[0].text。
    """
    block = MagicMock()
    block.text = text
    response = MagicMock()
    response.content = [block]
    return response


@pytest.fixture
def extractor() -> LLMExtractor:
    """构造 extractor —— anthropic_api_key 可为空，因为 client 不会真正调用"""
    return LLMExtractor()


def test_extract_happy_path_fever_with_chemo(extractor):
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

    with patch.object(
        extractor.client.messages, "create", return_value=_mock_response(fake_json)
    ) as mock_create:
        result = extractor.extract(
            "昨天打完化疗第三天，今天下午开始发烧 38.5 度，浑身发冷",
            SYMPTOMS,
        )

    # 调用了一次，传入了 grounding 后的 system prompt
    assert mock_create.call_count == 1
    call_kwargs = mock_create.call_args.kwargs
    assert "fever" in call_kwargs["system"]              # 字典 ID 嵌入了
    assert "发烧" in call_kwargs["system"]                # 别名嵌入了
    assert call_kwargs["temperature"] == 0.0              # 临床场景必须确定性

    # 抽取结果正确
    assert len(result.symptoms) == 1
    assert result.symptoms[0].symptom_id == "fever"
    assert result.symptoms[0].numeric_value == 38.5
    assert result.context["days_since_chemo"] == 3
    assert result.confidence is not None and result.confidence >= 0.8


def test_extract_handles_markdown_code_fence(extractor):
    """LLM 偶尔会在 JSON 外裹 ```json ... ```，应该兼容"""
    fake_json = """```json
    {
      "symptoms": [{"symptom_id": "nausea", "categorical_value": "mild"}],
      "context": {},
      "confidence": 0.7
    }
    ```"""

    with patch.object(
        extractor.client.messages, "create", return_value=_mock_response(fake_json)
    ):
        result = extractor.extract("有点想吐", SYMPTOMS)

    assert result.symptoms[0].symptom_id == "nausea"
    assert result.symptoms[0].categorical_value == "mild"


def test_extract_raises_on_garbage_response(extractor):
    """LLM 返回 'I don't know...' 这种没有 JSON 的乱码 → LLMExtractionError"""
    with patch.object(
        extractor.client.messages,
        "create",
        return_value=_mock_response("I don't know what you're talking about."),
    ):
        with pytest.raises(LLMExtractionError, match="No JSON"):
            extractor.extract("一些奇怪的输入", SYMPTOMS)


def test_extract_raises_on_unknown_symptom_id(extractor):
    """LLM 返回字典外的 symptom_id (如 'diabetes') → LLMExtractionError"""
    fake_json = json.dumps({
        "symptoms": [
            {"symptom_id": "diabetes", "categorical_value": "moderate"}
        ],
        "context": {},
        "confidence": 0.8,
    })

    with patch.object(
        extractor.client.messages, "create", return_value=_mock_response(fake_json)
    ):
        with pytest.raises(LLMExtractionError, match="not in dictionary"):
            extractor.extract("我有糖尿病", SYMPTOMS)


def test_extract_raises_on_schema_mismatch(extractor):
    """JSON 合法但不符合 ParsedSymptoms schema → LLMExtractionError"""
    # confidence > 1.0 违反 Field(ge=0, le=1) 约束
    fake_json = json.dumps({
        "symptoms": [{"symptom_id": "fever", "numeric_value": 38.0}],
        "context": {},
        "confidence": 5.0,
    })

    with patch.object(
        extractor.client.messages, "create", return_value=_mock_response(fake_json)
    ):
        with pytest.raises(LLMExtractionError, match="ParsedSymptoms schema"):
            extractor.extract("发烧 38 度", SYMPTOMS)


def test_extract_raises_on_api_error(extractor):
    """API 超时 / 限流 / 5xx 都被包装成 LLMExtractionError"""
    fake_request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    api_error = anthropic.APIConnectionError(request=fake_request)

    with patch.object(extractor.client.messages, "create", side_effect=api_error):
        with pytest.raises(LLMExtractionError, match="Anthropic API call failed"):
            extractor.extract("发烧", SYMPTOMS)


def test_extract_raises_on_empty_dictionary(extractor):
    """空字典是上游 bug，应立即报错而不是去调 LLM"""
    with pytest.raises(LLMExtractionError, match="dictionary_snapshot is empty"):
        extractor.extract("发烧", [])
