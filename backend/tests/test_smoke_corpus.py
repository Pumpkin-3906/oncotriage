"""真实患者语料的冒烟测试 —— 直接打 LLM API。

用法：
    pytest tests/test_smoke_corpus.py -m smoke -v

设计要点：
- 默认 pytest 跳过这些用例（@pytest.mark.smoke）
- 不 mock LLM —— 必须打真实 Anthropic API
- 断言宽松（must_include 而非 only_include；confidence 用区间）
- 同一次 LLM 抽取的结果同时喂给 CompletenessChecker，避免重复调 API

参考：docs/tasks/M_smoke_corpus.md
"""
from pathlib import Path

import pytest
import yaml

from app.rules.seed_dictionary import SYMPTOMS
from app.services.completeness_checker import CompletenessChecker
from app.services.llm_extractor import LLMExtractor

SMOKE_FILE = Path(__file__).parent / "smoke_cases.yaml"
CASES = yaml.safe_load(SMOKE_FILE.read_text(encoding="utf-8"))


# 模块级共享的 extractor —— 避免每个 case 都重新构造 client
# （client 自身无状态，重用安全；可省一点对象构造开销）
@pytest.fixture(scope="module")
def extractor() -> LLMExtractor:
    return LLMExtractor()


@pytest.mark.smoke
@pytest.mark.parametrize("case", CASES, ids=[c["id"] for c in CASES])
def test_llm_extraction(case, extractor):
    """对每条 smoke 输入，验证 LLM 抽取结果符合预期断言。

    断言策略：
    - must_include: 抽取结果必须含这些 symptom_id（不要求恰好等于）
    - must_not_include: 抽取结果绝不能含这些（防过度抽取）
    - extracted_context_keys: context 必含的键
    - confidence_min / confidence_max: 置信度区间
    """
    result = extractor.extract(case["input"], SYMPTOMS)
    expected = case.get("expected", {})

    actual_ids = {s.symptom_id for s in result.symptoms}

    # ── 必含的 symptom_id ────────────────────────────────────
    for must in expected.get("extracted_symptoms_must_include", []):
        assert must in actual_ids, (
            f"[{case['id']}] missing required symptom: {must!r}\n"
            f"  input  = {case['input']!r}\n"
            f"  got    = {sorted(actual_ids)}\n"
            f"  notes  = {case.get('notes', '')}"
        )

    # ── 绝不能含的 symptom_id ────────────────────────────────
    for forbidden in expected.get("extracted_symptoms_must_not_include", []):
        assert forbidden not in actual_ids, (
            f"[{case['id']}] forbidden symptom appeared: {forbidden!r}\n"
            f"  input  = {case['input']!r}\n"
            f"  got    = {sorted(actual_ids)}\n"
            f"  notes  = {case.get('notes', '')}"
        )

    # ── context 必含的键 ─────────────────────────────────────
    context = result.context or {}
    for key in expected.get("extracted_context_keys", []):
        assert key in context and context[key] is not None, (
            f"[{case['id']}] missing context key: {key!r}\n"
            f"  input   = {case['input']!r}\n"
            f"  context = {context}\n"
            f"  notes   = {case.get('notes', '')}"
        )

    # ── 置信度区间 ───────────────────────────────────────────
    if "confidence_min" in expected:
        assert result.confidence is not None, (
            f"[{case['id']}] confidence is None but confidence_min={expected['confidence_min']}"
        )
        assert result.confidence >= expected["confidence_min"], (
            f"[{case['id']}] confidence too low: "
            f"got {result.confidence:.2f}, want >= {expected['confidence_min']}\n"
            f"  notes = {case.get('notes', '')}"
        )
    if "confidence_max" in expected:
        assert result.confidence is not None, (
            f"[{case['id']}] confidence is None but confidence_max={expected['confidence_max']}"
        )
        assert result.confidence <= expected["confidence_max"], (
            f"[{case['id']}] confidence too high: "
            f"got {result.confidence:.2f}, want <= {expected['confidence_max']}\n"
            f"  notes = {case.get('notes', '')}"
        )

    # ── CompletenessChecker 断言 ─────────────────────────────
    # 与 LLM 抽取共用结果，避免重复调 API。
    # CompletenessChecker 是纯规则查表，确定性，"信息缺失"判断不依赖 LLM 自评。
    if "completeness" in expected:
        spec = expected["completeness"]
        completeness = CompletenessChecker(SYMPTOMS).check(result)

        if "is_complete" in spec:
            assert completeness.is_complete is spec["is_complete"], (
                f"[{case['id']}] completeness.is_complete mismatch: "
                f"got {completeness.is_complete}, want {spec['is_complete']}\n"
                f"  symptoms      = {[(s.symptom_id, s.numeric_value, s.ctcae_grade, s.categorical_value) for s in result.symptoms]}\n"
                f"  missing_slots = {[(m.symptom_id, m.missing_fields) for m in completeness.missing_slots]}\n"
                f"  notes         = {case.get('notes', '')}"
            )

        missing_ids = {m.symptom_id for m in completeness.missing_slots}
        for sid in spec.get("missing_slots_must_include", []):
            assert sid in missing_ids, (
                f"[{case['id']}] expected {sid!r} in missing_slots, "
                f"but only got {sorted(missing_ids)}\n"
                f"  symptoms = {[(s.symptom_id, s.numeric_value, s.ctcae_grade, s.categorical_value) for s in result.symptoms]}\n"
                f"  notes    = {case.get('notes', '')}"
            )
