"""感知层 —— LLM 抽取自由文本到结构化症状

对应 DESIGN.md §5.① 感知环节
- 模型: Claude Sonnet
- 输出约束: JSON Schema (Pydantic ParsedSymptoms)
- 词表 grounding: prompt 中嵌入 symptom_dictionary
- 失败兜底: 由 Orchestrator 决定是否走 checklist
"""
from anthropic import Anthropic

from app.config import settings
from app.schemas.assessment import ParsedSymptoms


class LLMExtractor:
    def __init__(self) -> None:
        self.client = Anthropic(api_key=settings.anthropic_api_key)
        self.model = settings.anthropic_model

    def extract(self, raw_text: str, dictionary_snapshot: list[dict]) -> ParsedSymptoms:
        """
        从 raw_text 中抽取症状，强制映射到 dictionary_snapshot 中的 symptom_id。

        TODO: 实现要点
        1. 构造 system prompt：含 symptom_dictionary 全表 + 输出 JSON schema
        2. 调用 messages.create() with max_tokens, temperature=0
        3. 解析 JSON 响应，校验为 ParsedSymptoms
        4. 异常路径：raise LLMExtractionError，由 Orchestrator 处理降级
        """
        raise NotImplementedError


class LLMExtractionError(Exception):
    """LLM 抽取失败 —— Orchestrator 据此决定降级到 checklist"""
    pass
