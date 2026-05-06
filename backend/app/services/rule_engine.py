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
        """Plan D: 评估全部，决策一条，审计全部

        `when: always: true` 视为 fallback：只在无具体规则命中时启用，
        贴合 R999_default_unmatched 的本意（避免 R999 与低风险规则共触发）。
        """
        matches: list[RuleMatch] = []
        fallback: list[RuleMatch] = []
        for rule in self.rules:
            if rule.get("requires_feature") == "timeseries" and trends is None:
                continue
            if self._matches(rule, parsed, trends):
                (fallback if self._is_fallback(rule) else matches).append(
                    self._to_match(rule, parsed, trends)
                )
        if not matches:
            matches = fallback

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

    @staticmethod
    def _is_fallback(rule: dict) -> bool:
        """`when: always: true` 即兜底规则"""
        return bool(rule.get("when", {}).get("always"))

    def _priority_of(self, rule_id: str) -> int:
        for r in self.rules:
            if r["id"] == rule_id:
                return r.get("priority", 99)
        return 99

    def _matches(self, rule: dict, parsed: ParsedSymptoms, trends: dict | None) -> bool:
        """求值 when 子句：all_of / any_of / always"""
        when = rule.get("when", {})
        if when.get("always"):
            return True
        if "all_of" in when:
            return all(self._eval_clause(c, parsed, trends) for c in when["all_of"])
        if "any_of" in when:
            return any(self._eval_clause(c, parsed, trends) for c in when["any_of"])
        return False

    def _to_match(self, rule: dict, parsed: ParsedSymptoms, trends: dict | None) -> RuleMatch:
        """打包 RuleMatch；matched_fields 收集命中时的具体值用于审计"""
        matched_fields: dict[str, Any] = {}
        when = rule.get("when", {})
        for clause in when.get("all_of", []) + when.get("any_of", []):
            if self._eval_clause(clause, parsed, trends):
                self._collect_matched_fields(clause, parsed, trends, matched_fields)

        return RuleMatch(
            rule_id=rule["id"],
            rule_version=self.engine_version,
            risk_level=rule["risk"],
            advice_template=rule["advice_template"],
            contact_team=rule.get("contact_team", False),
            urgency=rule.get("urgency", "next_visit"),
            source_doc=rule.get("source", ""),
            rationale_text=rule.get("rationale", "").strip(),
            matched_fields=matched_fields,
        )

    # ── 子句求值：派发到 symptom / context / trend 三类 ─────
    def _eval_clause(
        self, clause: dict, parsed: ParsedSymptoms, trends: dict | None
    ) -> bool:
        if "symptom" in clause:
            item = next(
                (s for s in parsed.symptoms if s.symptom_id == clause["symptom"]),
                None,
            )
            return item is not None and self._all_fields_match(
                clause, lambda f: getattr(item, f, None), skip="symptom"
            )
        if "context" in clause:
            return self._all_fields_match(
                clause["context"], lambda f: parsed.context.get(f)
            )
        if "trend" in clause:
            spec = clause["trend"]
            data = (trends or {}).get(spec.get("symptom"))
            return bool(data) and self._all_fields_match(
                spec, lambda f: data.get(f), skip="symptom"
            )
        return False

    @classmethod
    def _all_fields_match(cls, fields: dict, getter, skip: str | None = None) -> bool:
        """对 fields 里每个 (key, constraint)，用 getter(key) 取实际值再比较"""
        for f, spec in fields.items():
            if f == skip:
                continue
            if not cls._eval_value_constraint(getter(f), spec):
                return False
        return True

    _OPS = {
        "gte": lambda a, t: a >= t,
        "gt":  lambda a, t: a > t,
        "lte": lambda a, t: a <= t,
        "lt":  lambda a, t: a < t,
        "eq":  lambda a, t: a == t,
        "in":  lambda a, t: a in t,
    }

    @classmethod
    def _eval_value_constraint(cls, actual: Any, spec: Any) -> bool:
        """spec 不是 dict 时视为 {eq: spec} 简写；actual is None 一律不命中"""
        if not isinstance(spec, dict):
            return actual == spec
        if actual is None:
            return False
        for op, target in spec.items():
            if op not in cls._OPS:
                raise ValueError(f"Unknown operator in rule: {op!r}")
            if not cls._OPS[op](actual, target):
                return False
        return True

    def _collect_matched_fields(
        self,
        clause: dict,
        parsed: ParsedSymptoms,
        trends: dict | None,
        out: dict[str, Any],
    ) -> None:
        """把命中子句的实际值写入 audit dict"""
        if "symptom" in clause:
            sid = clause["symptom"]
            item = next(s for s in parsed.symptoms if s.symptom_id == sid)
            for field in clause:
                if field == "symptom":
                    continue
                out[f"symptom_{sid}_{field}"] = getattr(item, field, None)
        elif "context" in clause:
            for field in clause["context"]:
                out[f"context_{field}"] = parsed.context.get(field)
        elif "trend" in clause:
            sid = clause["trend"].get("symptom")
            data = (trends or {}).get(sid, {})
            for field in clause["trend"]:
                if field == "symptom":
                    continue
                out[f"trend_{sid}_{field}"] = data.get(field)
