"""感知层 —— LLM 抽取自由文本到结构化症状

对应 DESIGN.md §5.① 感知环节
- 模型: Claude Sonnet / OpenAI 兼容（DeepSeek/Qwen/...）
- 输出约束: JSON Schema (Pydantic ParsedSymptoms)
- 词表 grounding: prompt 中嵌入 symptom_dictionary
- 失败兜底: 由 Orchestrator 决定是否走 checklist

Extractor 与具体 SDK 解耦：通过 LLMClient 协议调用底层。
切换 provider 只需改 settings.llm_provider，不改本文件。
"""
import json
import re

from pydantic import ValidationError

from app.schemas.assessment import ParsedSymptoms
from app.services.llm_client import (
    LLMClient,
    LLMClientError,
    build_default_llm_client,
)


class LLMExtractionError(Exception):
    """LLM 抽取失败 —— Orchestrator 据此决定降级到 checklist"""
    pass


SYSTEM_PROMPT_TEMPLATE = """你是一个临床症状抽取助手。从用户描述中识别症状并映射到下表 ID。

【严格规则】
1. symptom_id 必须从下表精确选择，不在表中的症状必须丢弃，不要凭空创造
2. 输出严格的 JSON 对象，不要任何解释文字、不要 markdown 围栏
3. 模糊或不确定的描述，相应降低 confidence (0.0-1.0)
4. value_type=numeric 的症状（如 fever）：填 numeric_value（数字，如体温 38.5），不填 ctcae_grade
5. value_type=categorical 的症状：可填 ctcae_grade(1-5) 或 categorical_value(mild|moderate|severe)
6. duration_hours / interferes_with_adl 不知道留 null
7. context.days_since_chemo：如果用户提到"化疗第 N 天 / 打完化疗 N 天"，填整数 N；否则 null

【可用症状字典】
{dictionary_block}

【输出 JSON 严格格式】
{{
  "symptoms": [
    {{
      "symptom_id": "<上表 id 之一>",
      "numeric_value": <number|null>,
      "numeric_unit": <string|null>,
      "categorical_value": <"mild"|"moderate"|"severe"|null>,
      "ctcae_grade": <1-5|null>,
      "duration_hours": <number|null>,
      "interferes_with_adl": <true|false|null>
    }}
  ],
  "context": {{"days_since_chemo": <int|null>}},
  "confidence": <0.0-1.0>
}}

只输出 JSON，不要任何其他文字。"""


def _format_dictionary(snapshot: list[dict]) -> str:
    """把 12 条字典渲染成 prompt 中的受控词表块"""
    lines = []
    for s in snapshot:
        aliases = "、".join(s.get("aliases_zh") or [])
        lines.append(
            f"- {s['id']}: {s['display_name_zh']} "
            f"(value_type={s['value_type']}, grading={s.get('grading_scheme', 'n/a')}) "
            f"/ 别名: {aliases}"
        )
    return "\n".join(lines)


def _extract_json_blob(text: str) -> dict:
    """从 LLM 响应中提取 JSON 对象，兼容 ```json ... ``` 围栏与前后多余文字"""
    text = text.strip()
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise LLMExtractionError(f"No JSON object found in LLM response: {text[:200]!r}")
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError as e:
        raise LLMExtractionError(f"LLM response is not valid JSON: {e}") from e


class LLMExtractor:
    def __init__(self, client: LLMClient | None = None) -> None:
        """构造 Extractor。

        client=None 时按 settings.llm_provider 自动构造（生产用法）；
        测试可注入 FakeLLMClient 绕过真实 SDK。
        """
        self.client = client if client is not None else build_default_llm_client()

    @property
    def model(self) -> str:
        """暴露给审计：assessment.extraction_model_version 写这个值"""
        return self.client.model

    def extract(self, raw_text: str, dictionary_snapshot: list[dict]) -> ParsedSymptoms:
        """从 raw_text 抽取症状，强制映射到 dictionary_snapshot 中的 symptom_id。

        失败路径全部抛 LLMExtractionError：
        - dictionary_snapshot 为空（上游 bug）
        - LLMClient 抛 LLMClientError（API 超时 / 限流 / 5xx）
        - 响应非合法 JSON
        - JSON 不符合 ParsedSymptoms 结构
        - symptom_id 不在字典里
        """
        if not dictionary_snapshot:
            raise LLMExtractionError("dictionary_snapshot is empty")

        valid_ids = {s["id"] for s in dictionary_snapshot}
        system_prompt = SYSTEM_PROMPT_TEMPLATE.format(
            dictionary_block=_format_dictionary(dictionary_snapshot)
        )

        try:
            text = self.client.complete(system_prompt, raw_text)
        except LLMClientError as e:
            raise LLMExtractionError(str(e)) from e

        data = _extract_json_blob(text)

        try:
            parsed = ParsedSymptoms.model_validate(data)
        except ValidationError as e:
            raise LLMExtractionError(f"LLM JSON does not match ParsedSymptoms schema: {e}") from e

        unknown = [s.symptom_id for s in parsed.symptoms if s.symptom_id not in valid_ids]
        if unknown:
            raise LLMExtractionError(
                f"LLM returned symptom_id(s) not in dictionary: {unknown}"
            )

        return parsed
