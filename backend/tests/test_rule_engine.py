"""规则引擎 7 个 case 单测 —— 覆盖 docs/tasks/M3 必填表格"""
import pytest

from app.rules.loader import load_rules
from app.schemas.assessment import ParsedSymptoms, SymptomItem
from app.services.rule_engine import RuleEngine


@pytest.fixture
def engine(rules_path):
    bundle = load_rules(rules_path)
    return RuleEngine(bundle.rules, bundle.engine_version)


def test_post_chemo_high_fever_hits_R001(engine):
    """化疗后 ≥38.3℃ 高烧 → R001 high"""
    parsed = ParsedSymptoms(
        symptoms=[SymptomItem(symptom_id="fever", numeric_value=38.5)],
        context={"days_since_chemo": 3},
    )
    result = engine.evaluate(parsed)
    assert result.final_risk_level == "high"
    assert result.primary.rule_id.startswith("R001")
    # matched_fields 审计：实际温度和化疗天数都要写入
    mf = result.primary.matched_fields
    assert mf.get("symptom_fever_numeric_value") == 38.5
    assert mf.get("context_days_since_chemo") == 3


def test_post_chemo_persistent_low_fever_hits_R002(engine):
    """化疗后 38.0–38.3℃ 持续 ≥1h → R002 high"""
    parsed = ParsedSymptoms(
        symptoms=[
            SymptomItem(symptom_id="fever", numeric_value=38.1, duration_hours=2)
        ],
        context={"days_since_chemo": 5},
    )
    result = engine.evaluate(parsed)
    assert result.final_risk_level == "high"
    assert result.primary.rule_id.startswith("R002")


def test_severe_diarrhea_hits_R004(engine):
    """CTCAE G3+ 腹泻 → R004 high"""
    parsed = ParsedSymptoms(
        symptoms=[SymptomItem(symptom_id="severe_diarrhea", ctcae_grade=3)],
        context={},
    )
    result = engine.evaluate(parsed)
    assert result.final_risk_level == "high"
    assert result.primary.rule_id.startswith("R004")


def test_grade2_hand_foot_hits_R010(engine):
    """G2 手足综合征 → R010 medium"""
    parsed = ParsedSymptoms(
        symptoms=[SymptomItem(symptom_id="hand_foot_skin_reaction", ctcae_grade=2)],
        context={},
    )
    result = engine.evaluate(parsed)
    assert result.final_risk_level == "medium"
    assert result.primary.rule_id.startswith("R010")


def test_mild_nausea_hits_R020(engine):
    """G1 恶心 → R020 low"""
    parsed = ParsedSymptoms(
        symptoms=[SymptomItem(symptom_id="nausea", ctcae_grade=1)],
        context={},
    )
    result = engine.evaluate(parsed)
    assert result.final_risk_level == "low"
    assert result.primary.rule_id.startswith("R020")


def test_empty_input_hits_R999_default(engine):
    """空 symptoms → R999 兜底 medium"""
    parsed = ParsedSymptoms(symptoms=[], context={})
    result = engine.evaluate(parsed)
    assert result.final_risk_level == "medium"
    assert result.primary.rule_id.startswith("R999")


def test_multiple_rules_match_plan_d(engine):
    """Plan D 关键 case：高烧 + 化疗后 + 轻度恶心
    R001 (high) 和 R020 (low) 都命中；primary=R001，all_matches ≥ 2，final=high
    """
    parsed = ParsedSymptoms(
        symptoms=[
            SymptomItem(symptom_id="fever", numeric_value=38.5),
            SymptomItem(symptom_id="nausea", ctcae_grade=1),
        ],
        context={"days_since_chemo": 3},
    )
    result = engine.evaluate(parsed)
    assert result.final_risk_level == "high"
    assert result.primary.rule_id.startswith("R001")
    assert len(result.all_matches) >= 2
    matched_ids = {m.rule_id for m in result.all_matches}
    assert any(rid.startswith("R001") for rid in matched_ids)
    assert any(rid.startswith("R020") for rid in matched_ids)
