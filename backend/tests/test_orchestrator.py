"""Orchestrator 集成测试 —— mock LLM Extractor，使用真实 DB。

覆盖任务卡 4 个必需 case：
  1. happy path（化疗后高烧）→ risk='high'，4 张表都有数据
  2. 幂等：同 key 提交两次 → 第二次复用首次结果，DB assessment 行数==1
  3. LLM 失败 → raise LLMExtractionError，DB 无新记录
  4. 规则引擎崩溃 → Tx1 数据保留，assessment.decision_status='failed'
"""
import uuid
from uuid import uuid4

import pytest
import sqlalchemy as sa

from app.db import SessionLocal
from app.models import Advice as AdviceModel
from app.models import Assessment, Evidence, SymptomObservation
from app.rules.loader import load_rules
from app.config import settings
from app.schemas.assessment import (
    AssessmentRequest,
    ParsedSymptoms,
    SymptomItem,
)
from app.services.llm_extractor import LLMExtractionError, LLMExtractor
from app.services.orchestrator import Orchestrator


# ── 测试用 stubs ──────────────────────────────────────────────


class FakeExtractor:
    """实现 LLMExtractor 公共接口（extract / model）。

    可注入任意 ParsedSymptoms 或异常；记录 .calls 用于断言"被调几次"。
    """

    model = "fake-extractor-v1"

    def __init__(self, parsed: ParsedSymptoms | None = None, error: Exception | None = None):
        self._parsed = parsed
        self._error = error
        self.calls = 0

    def extract(self, raw_text: str, dictionary: list[dict]) -> ParsedSymptoms:
        self.calls += 1
        if self._error is not None:
            raise self._error
        assert self._parsed is not None
        return self._parsed


# ── 通用 fixtures ─────────────────────────────────────────────


@pytest.fixture
def db():
    """每个测试一个 Session；teardown 时清掉本测试创建的 user 及级联数据。"""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def test_user(db):
    """创建临时 user，结束时删除（级联清掉 assessment / advice / evidence / symptom_observation）。"""
    user_id = uuid4()
    db.execute(
        sa.text("INSERT INTO users (id, external_id) VALUES (:id, :ext)"),
        {"id": user_id, "ext": f"orchestrator_test_{user_id}"},
    )
    db.commit()
    yield user_id
    # 清理：先删 advice/evidence/symptom_observation/assessment/contact_request/case_review，再删 user
    for stmt in (
        "DELETE FROM advice WHERE assessment_id IN (SELECT id FROM assessment WHERE user_id = :uid)",
        "DELETE FROM evidence WHERE assessment_id IN (SELECT id FROM assessment WHERE user_id = :uid)",
        "DELETE FROM symptom_observation WHERE user_id = :uid",
        "DELETE FROM contact_request WHERE user_id = :uid",
        "DELETE FROM case_review WHERE user_id = :uid",
        "DELETE FROM assessment WHERE user_id = :uid",
        "DELETE FROM users WHERE id = :uid",
    ):
        db.execute(sa.text(stmt), {"uid": user_id})
    db.commit()


@pytest.fixture
def rules_bundle():
    return load_rules(settings.rules_path)


def _make_request(user_id: uuid.UUID, raw: str = "化疗后发烧 38.5") -> AssessmentRequest:
    return AssessmentRequest(
        user_id=user_id,
        session_id="test-session",
        input_source="free_text",
        idempotency_key=str(uuid4()),
        raw_input_text=raw,
    )


def _high_fever_parsed() -> ParsedSymptoms:
    return ParsedSymptoms(
        symptoms=[SymptomItem(symptom_id="fever", numeric_value=38.5)],
        context={"days_since_chemo": 3},
        confidence=0.9,
    )


# ── Cases ─────────────────────────────────────────────────────


def test_happy_path_post_chemo_high_fever(db, test_user, rules_bundle):
    """化疗后高烧 → high + R001；assessment / symptom_observation / evidence / advice 都有数据。"""
    extractor = FakeExtractor(parsed=_high_fever_parsed())
    req = _make_request(test_user)

    result = Orchestrator(db, extractor=extractor, rules_bundle=rules_bundle).run(req)

    assert result.risk_level == "high"
    assert result.audit.matched_rules[0].rule_id.startswith("R001")
    assert result.advice.contact_team is True
    assert result.advice.urgency == "now_24h"
    # assessment_id 应被嵌入渲染文本
    assert str(result.assessment_id) in result.advice.text

    # 4 张表都应有数据
    assess = db.query(Assessment).filter(Assessment.id == result.assessment_id).one()
    assert assess.decision_status == "completed"
    assert assess.risk_level == "high"
    assert assess.rule_engine_version == rules_bundle.engine_version
    assert assess.extraction_model_version == "fake-extractor-v1"

    obs_count = db.query(SymptomObservation).filter(
        SymptomObservation.assessment_id == result.assessment_id
    ).count()
    assert obs_count == 1

    ev_count = db.query(Evidence).filter(
        Evidence.assessment_id == result.assessment_id
    ).count()
    assert ev_count >= 1

    advice_count = db.query(AdviceModel).filter(
        AdviceModel.assessment_id == result.assessment_id
    ).count()
    assert advice_count == 1


def test_idempotency_same_key_returns_cached_result(db, test_user, rules_bundle):
    """同 (user_id, idempotency_key) 提交两次 → 第二次直接返回首次结果，不再调 LLM。"""
    extractor = FakeExtractor(parsed=_high_fever_parsed())
    req = _make_request(test_user)

    orch = Orchestrator(db, extractor=extractor, rules_bundle=rules_bundle)
    first = orch.run(req)
    second = orch.run(req)

    # LLM 只调一次
    assert extractor.calls == 1
    # 同一个 assessment_id
    assert first.assessment_id == second.assessment_id
    assert first.risk_level == second.risk_level
    # DB 中只有 1 行 assessment
    n = db.query(Assessment).filter(Assessment.user_id == test_user).count()
    assert n == 1


def test_llm_failure_raises_and_writes_no_rows(db, test_user, rules_bundle):
    """LLM 抛 LLMExtractionError → 直接传播，DB 无新 assessment 行。"""
    extractor = FakeExtractor(error=LLMExtractionError("simulated failure"))
    req = _make_request(test_user)

    with pytest.raises(LLMExtractionError):
        Orchestrator(db, extractor=extractor, rules_bundle=rules_bundle).run(req)

    n = db.query(Assessment).filter(Assessment.user_id == test_user).count()
    assert n == 0


def test_rule_engine_crash_marks_decision_failed(
    db, test_user, rules_bundle, monkeypatch
):
    """规则引擎抛错 → Tx1 数据保留，assessment.decision_status='failed'。"""
    extractor = FakeExtractor(parsed=_high_fever_parsed())
    req = _make_request(test_user)

    # 让 RuleEngine.evaluate 抛错（patch 实际被 orchestrator 引用的符号）
    from app.services import orchestrator as orch_mod

    def _boom(self, parsed, trends=None):
        raise RuntimeError("simulated rule engine crash")

    monkeypatch.setattr(orch_mod.RuleEngine, "evaluate", _boom)

    with pytest.raises(RuntimeError):
        Orchestrator(db, extractor=extractor, rules_bundle=rules_bundle).run(req)

    # Tx1 仍 commit：assessment + symptom_observation 都在
    assess = (
        db.query(Assessment)
        .filter(Assessment.user_id == test_user)
        .one()
    )
    assert assess.decision_status == "failed"
    assert assess.risk_level is None
    assert assess.rule_engine_version is None

    obs_count = (
        db.query(SymptomObservation)
        .filter(SymptomObservation.assessment_id == assess.id)
        .count()
    )
    assert obs_count == 1

    # Tx2 失败：evidence / advice 表无该 assessment 数据
    ev_count = db.query(Evidence).filter(Evidence.assessment_id == assess.id).count()
    advice_count = db.query(AdviceModel).filter(AdviceModel.assessment_id == assess.id).count()
    assert ev_count == 0
    assert advice_count == 0
