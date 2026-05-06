"""验证 rules.yaml 能被加载，且关键字段齐全"""
from app.rules.loader import load_rules


def test_load_rules_yaml(rules_path):
    bundle = load_rules(rules_path)

    # 引擎版本号存在
    assert bundle.engine_version

    # 至少 11 条规则（设计文档承诺）
    assert len(bundle.rules) >= 11

    # 兜底规则存在
    rule_ids = {r["id"] for r in bundle.rules}
    assert "R999_default_unmatched" in rule_ids

    # 三个风险级都覆盖
    risk_levels = {r["risk"] for r in bundle.rules}
    assert {"high", "medium", "low"} <= risk_levels

    # 每条规则都有审计需要的 source 字段
    for rule in bundle.rules:
        assert "source" in rule, f"Rule {rule['id']} missing 'source'"
        assert "rationale" in rule, f"Rule {rule['id']} missing 'rationale'"

    # 4 个建议模板都在
    expected_templates = {
        "tpl_emergency_er",
        "tpl_contact_team_48h",
        "tpl_observe_and_log",
        "tpl_contact_team_when_convenient",
    }
    assert expected_templates <= set(bundle.advice_templates.keys())
