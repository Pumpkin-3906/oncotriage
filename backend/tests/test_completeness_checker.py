"""完整性检查器 8 个 case 单测 —— 覆盖 docs/tasks/M3 Part B 必填表格"""
import pytest

from app.rules.seed_dictionary import SYMPTOMS
from app.schemas.assessment import ParsedSymptoms, SymptomItem
from app.services.completeness_checker import CompletenessChecker


@pytest.fixture
def checker():
    return CompletenessChecker(SYMPTOMS)


def test_numeric_field_present(checker):
    """fever (numeric) 带 numeric_value → complete"""
    parsed = ParsedSymptoms(
        symptoms=[SymptomItem(symptom_id="fever", numeric_value=38.5)],
        context={},
    )
    result = checker.check(parsed)
    assert result.is_complete
    assert result.missing_slots == []


def test_numeric_field_missing(checker):
    """fever 没 numeric_value → incomplete, missing=['numeric_value']"""
    parsed = ParsedSymptoms(
        symptoms=[SymptomItem(symptom_id="fever")],
        context={},
    )
    result = checker.check(parsed)
    assert not result.is_complete
    assert len(result.missing_slots) == 1
    slot = result.missing_slots[0]
    assert slot.symptom_id == "fever"
    assert slot.missing_fields == ["numeric_value"]


def test_categorical_with_grade(checker):
    """nausea (categorical) 带 ctcae_grade → complete"""
    parsed = ParsedSymptoms(
        symptoms=[SymptomItem(symptom_id="nausea", ctcae_grade=2)],
        context={},
    )
    assert checker.check(parsed).is_complete


def test_categorical_with_categorical_value(checker):
    """nausea 带 categorical_value（无 grade）也 OK → complete"""
    parsed = ParsedSymptoms(
        symptoms=[SymptomItem(symptom_id="nausea", categorical_value="moderate")],
        context={},
    )
    assert checker.check(parsed).is_complete


def test_categorical_missing_both(checker):
    """nausea ctcae_grade 与 categorical_value 都没 → incomplete"""
    parsed = ParsedSymptoms(
        symptoms=[SymptomItem(symptom_id="nausea")],
        context={},
    )
    result = checker.check(parsed)
    assert not result.is_complete
    slot = result.missing_slots[0]
    assert slot.symptom_id == "nausea"
    # 期望同时列出 ctcae_grade 与 categorical_value（顺序可任）
    assert set(slot.missing_fields) == {"ctcae_grade", "categorical_value"}


def test_unknown_symptom_id(checker):
    """字典里没有的 symptom_id → incomplete + 标识 unknown"""
    parsed = ParsedSymptoms(
        symptoms=[SymptomItem(symptom_id="diabetes")],
        context={},
    )
    result = checker.check(parsed)
    assert not result.is_complete
    slot = result.missing_slots[0]
    assert slot.symptom_id == "diabetes"
    assert slot.missing_fields == ["unknown_symptom_in_dictionary"]


def test_empty_symptoms(checker):
    """空 symptoms → complete（让规则引擎 R999 兜底）"""
    parsed = ParsedSymptoms(symptoms=[], context={})
    result = checker.check(parsed)
    assert result.is_complete
    assert result.missing_slots == []


def test_mixed_complete_and_missing(checker):
    """fever 完整 + nausea 缺信息 → incomplete, len(missing)==1"""
    parsed = ParsedSymptoms(
        symptoms=[
            SymptomItem(symptom_id="fever", numeric_value=38.5),
            SymptomItem(symptom_id="nausea"),  # 没 grade 也没 categorical_value
        ],
        context={},
    )
    result = checker.check(parsed)
    assert not result.is_complete
    assert len(result.missing_slots) == 1
    assert result.missing_slots[0].symptom_id == "nausea"
