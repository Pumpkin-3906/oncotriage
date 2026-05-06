"""决策层 —— YAML 规则引擎

对应 DESIGN.md §5.② 决策环节
- 策略: Plan D — 评估全部，决策一条，审计全部
  1. 跑完所有规则，收集所有命中
  2. risk_level = max(命中规则的 risks)   # high > medium > low
  3. 主建议 = 在 max 风险等级里，priority 最小的那条
  4. evidence 表记录所有命中（不止主建议那条）
- 规则源: docs/rules/rules.yaml
"""
from dataclasses import dataclass
from typing import Any

from app.schemas.assessment import ParsedSymptoms


RISK_RANK = {"high": 3, "medium": 2, "low": 1}


@dataclass
class RuleMatch:
    rule_id: str
    rule_version: str
    risk_level: str
    advice_template: str
    contact_team: bool
    urgency: str
    source_doc: str
    rationale_text: str
    matched_fields: dict[str, Any]


@dataclass
class EvaluationResult:
    """规则引擎的完整输出 —— Plan D"""
    primary: RuleMatch              # 用于渲染建议
    all_matches: list[RuleMatch]    # 全部命中，写入 evidence 表
    final_risk_level: str           # 最高风险等级
    used_timeseries: bool           # 是否用了 trend 数据


class RuleEngine:
    def __init__(self, rules: list[dict], engine_version: str):
        self.rules = rules
        self.engine_version = engine_version

    def evaluate(
        self,
        parsed: ParsedSymptoms,
        trends: dict | None = None,
    ) -> EvaluationResult:
        """Plan D: 评估全部，决策一条，审计全部"""
        matches: list[RuleMatch] = []

        for rule in self.rules:
            # 跳过需要时序但当前关闭的规则
            if rule.get("requires_feature") == "timeseries" and trends is None:
                continue
            if self._matches(rule, parsed, trends):
                matches.append(self._to_match(rule, parsed, trends))

        if not matches:
            raise RuntimeError(
                "No rule matched. R999 default rule should always match — "
                "check rules.yaml integrity."
            )

        # 取最高风险等级
        final_risk = max(matches, key=lambda m: RISK_RANK[m.risk_level]).risk_level

        # 同最高风险里，priority 最小的作为 primary
        candidates = [m for m in matches if m.risk_level == final_risk]
        # priority 从原 rule 取，需要重新查找
        primary = min(candidates, key=lambda m: self._priority_of(m.rule_id))

        return EvaluationResult(
            primary=primary,
            all_matches=matches,
            final_risk_level=final_risk,
            used_timeseries=trends is not None,
        )

    def _priority_of(self, rule_id: str) -> int:
        for r in self.rules:
            if r["id"] == rule_id:
                return r.get("priority", 99)
        return 99

    def _matches(self, rule: dict, parsed: ParsedSymptoms, trends: dict | None) -> bool:
        """TODO: 实现 when 子句的 all_of / any_of / always 求值

        when 子句结构（见 rules.yaml）:
          all_of: [...]   每条都要满足
          any_of: [...]   任一满足即可
          always: true    兜底
        每个子条件可引用 symptom / context / trend
        """
        when = rule.get("when", {})
        if when.get("always"):
            return True
        # TODO: 实现 all_of / any_of 的求值
        raise NotImplementedError

    def _to_match(self, rule: dict, parsed: ParsedSymptoms, trends: dict | None) -> RuleMatch:
        """把 rule dict + 命中上下文打包成 RuleMatch"""
        # TODO: matched_fields 应记录命中时具体的症状值（用于审计）
        return RuleMatch(
            rule_id=rule["id"],
            rule_version=self.engine_version,
            risk_level=rule["risk"],
            advice_template=rule["advice_template"],
            contact_team=rule.get("contact_team", False),
            urgency=rule.get("urgency", "next_visit"),
            source_doc=rule.get("source", ""),
            rationale_text=rule.get("rationale", "").strip(),
            matched_fields={},  # TODO
        )
