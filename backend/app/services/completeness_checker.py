"""完整性检查器 —— 决策层前置过滤

对应 DESIGN.md §3 决策 #1：判断"信息够不够"是结构化问题，规则查表毫秒搞定。
LLM 抽到 "我发烧" 但没说几度时，发现并显式信号给 Orchestrator，由它决定追问 / 兜底。
本模块只检查，不改 ParsedSymptoms，也不调 LLM。
"""
from dataclasses import dataclass, field

from app.schemas.assessment import ParsedSymptoms


# 每种 value_type 对应若干"满足条件之一即可"的字段组
# 内层 list = AND（这组里全部要有值），外层 list = OR（任一组满足即可）
REQUIRED_BY_VALUE_TYPE: dict[str, list[list[str]]] = {
    "numeric":     [["numeric_value"]],
    "categorical": [["ctcae_grade"], ["categorical_value"]],
    "binary":      [],  # 存在即可
}


@dataclass
class MissingSlot:
    symptom_id: str
    missing_fields: list[str]  # 缺这些里任意一个有值就 OK；都缺才视为 incomplete


@dataclass
class CompletenessResult:
    is_complete: bool
    missing_slots: list[MissingSlot] = field(default_factory=list)


class CompletenessChecker:
    def __init__(self, dictionary: list[dict]):
        # 索引化，O(1) 查 value_type
        self.dictionary_index = {s["id"]: s for s in dictionary}

    def check(self, parsed: ParsedSymptoms) -> CompletenessResult:
        """空 symptoms → complete（让 R999 兜底处理）；否则逐个症状检查。"""
        if not parsed.symptoms:
            return CompletenessResult(is_complete=True)

        missing: list[MissingSlot] = []
        for item in parsed.symptoms:
            entry = self.dictionary_index.get(item.symptom_id)
            if entry is None:
                missing.append(MissingSlot(
                    symptom_id=item.symptom_id,
                    missing_fields=["unknown_symptom_in_dictionary"],
                ))
                continue

            value_type = entry.get("value_type", "binary")
            field_groups = REQUIRED_BY_VALUE_TYPE.get(value_type, [])
            if not field_groups:
                # binary 或未知 value_type：存在即可
                continue

            # 任一组完全填上即视为完整
            if any(
                all(getattr(item, f, None) is not None for f in group)
                for group in field_groups
            ):
                continue

            # 都没填：列出该 value_type 期望的字段（去重保序）
            wanted: list[str] = []
            for group in field_groups:
                for f in group:
                    if f not in wanted:
                        wanted.append(f)
            missing.append(MissingSlot(
                symptom_id=item.symptom_id,
                missing_fields=wanted,
            ))

        return CompletenessResult(
            is_complete=not missing,
            missing_slots=missing,
        )
