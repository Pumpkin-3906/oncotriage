"""POST /api/v1/assessments 集成测试 —— TestClient + 真实 DB + mock LLM。

覆盖任务卡 3 个必需 case：
  1. happy path → 201 + AssessmentResult，event_log 有 assessment_submitted 行
  2. 幂等：同 idempotency_key 提交两次 → 都 201，返回相同 assessment_id
  3. LLM 失败 → 422 + checklist_url 字段
"""
from __future__ import annotations

from uuid import uuid4

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient

from app.db import SessionLocal, get_db
from app.main import app
from app.rules.loader import load_rules
from app.config import settings
from app.schemas.assessment import ParsedSymptoms, SymptomItem
from app.services import orchestrator as orchestrator_module
from app.services.llm_extractor import LLMExtractionError


# ── Stubs ────────────────────────────────────────────────────


class _FakeExtractor:
    """实现 LLMExtractor 公共接口（extract / model）。"""

    model = "fake-extractor-v1"

    def __init__(
        self,
        parsed: ParsedSymptoms | None = None,
        error: Exception | None = None,
    ):
        self._parsed = parsed
        self._error = error
        self.calls = 0

    def extract(self, raw_text: str, dictionary: list[dict]) -> ParsedSymptoms:
        self.calls += 1
        if self._error is not None:
            raise self._error
        assert self._parsed is not None
        return self._parsed


def _high_fever_parsed() -> ParsedSymptoms:
    return ParsedSymptoms(
        symptoms=[SymptomItem(symptom_id="fever", numeric_value=38.5)],
        context={"days_since_chemo": 3},
        confidence=0.9,
    )


# ── Fixtures ─────────────────────────────────────────────────


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def test_user(db):
    """临时 user，结束清理本测试创建的 assessment / event_log / 级联数据。"""
    user_id = uuid4()
    db.execute(
        sa.text("INSERT INTO users (id, external_id) VALUES (:id, :ext)"),
        {"id": user_id, "ext": f"api_test_{user_id}"},
    )
    db.commit()
    yield user_id
    for stmt in (
        "DELETE FROM event_log WHERE user_id = :uid",
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
def client_with_extractor(db):
    """构造 TestClient，注入：
       1. get_db override → 复用本测试 fixture 的 db Session（保证看到同一份数据）
       2. monkeypatch Orchestrator → 自动注入指定的 FakeExtractor + rules_bundle

    返回 (client, install_extractor)；install_extractor(extractor) 用来切换 stub。
    """
    bundle = load_rules(settings.rules_path)
    state: dict = {"extractor": None}

    original_init = orchestrator_module.Orchestrator.__init__

    def patched_init(self, db_session, extractor=None, rules_bundle=None):
        original_init(
            self,
            db_session,
            extractor=extractor or state["extractor"],
            rules_bundle=rules_bundle or bundle,
        )

    orchestrator_module.Orchestrator.__init__ = patched_init
    app.dependency_overrides[get_db] = lambda: db

    def install(extractor):
        state["extractor"] = extractor

    try:
        with TestClient(app) as c:
            yield c, install
    finally:
        orchestrator_module.Orchestrator.__init__ = original_init
        app.dependency_overrides.pop(get_db, None)


def _payload(user_id, idem_key: str | None = None) -> dict:
    return {
        "user_id": str(user_id),
        "session_id": "api-test-session",
        "input_source": "free_text",
        "idempotency_key": idem_key or str(uuid4()),
        "raw_input_text": "化疗后发烧 38.5 度",
    }


# ── Cases ────────────────────────────────────────────────────


def test_happy_path_returns_201_and_emits_event(db, test_user, client_with_extractor):
    """201 + AssessmentResult；event_log 有 assessment_submitted 行。"""
    client, install = client_with_extractor
    install(_FakeExtractor(parsed=_high_fever_parsed()))

    body = _payload(test_user)
    resp = client.post("/api/v1/assessments", json=body)

    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["risk_level"] == "high"
    assert data["advice"]["contact_team"] is True
    assert data["advice"]["urgency"] == "now_24h"
    assert data["audit"]["matched_rules"][0]["rule_id"].startswith("R001")

    # event_log 应有该 user/session 的 assessment_submitted 行
    db.commit()  # 让本 Session 看到 EventEmitter 提交的行
    row = db.execute(
        sa.text(
            "SELECT event_type, session_id, assessment_id, payload "
            "FROM event_log WHERE user_id = :uid AND event_type = 'assessment_submitted'"
        ),
        {"uid": test_user},
    ).mappings().one()
    assert row["session_id"] == body["session_id"]
    assert str(row["assessment_id"]) == data["assessment_id"]
    assert row["payload"]["input_length"] == len(body["raw_input_text"])


def test_idempotent_post_returns_same_assessment_id(
    db, test_user, client_with_extractor
):
    """同 idempotency_key 两次提交 → 都 201，返回相同 assessment_id，LLM 仅调一次。"""
    client, install = client_with_extractor
    extractor = _FakeExtractor(parsed=_high_fever_parsed())
    install(extractor)

    body = _payload(test_user, idem_key=f"idem-{uuid4()}")
    r1 = client.post("/api/v1/assessments", json=body)
    r2 = client.post("/api/v1/assessments", json=body)

    assert r1.status_code == 201, r1.text
    assert r2.status_code == 201, r2.text
    assert r1.json()["assessment_id"] == r2.json()["assessment_id"]
    # LLM 只在首次抽取
    assert extractor.calls == 1

    # DB 仅 1 行 assessment
    db.commit()
    n = db.execute(
        sa.text("SELECT COUNT(*) FROM assessment WHERE user_id = :uid"),
        {"uid": test_user},
    ).scalar_one()
    assert n == 1


def test_post_with_parsed_symptoms_skips_llm(db, test_user, client_with_extractor):
    """传 parsed_symptoms 时 Orchestrator 不调 LLM extract，直接进规则引擎。"""
    client, install = client_with_extractor
    extractor = _FakeExtractor(parsed=_high_fever_parsed())
    install(extractor)

    body = _payload(test_user, idem_key=f"confirmed-{uuid4()}")
    body["parsed_symptoms"] = {
        "symptoms": [{"symptom_id": "fever", "numeric_value": 38.5}],
        "context": {"days_since_chemo": 3},
        "confidence": 1.0,
    }
    resp = client.post("/api/v1/assessments", json=body)

    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["risk_level"] == "high"
    assert data["audit"]["matched_rules"][0]["rule_id"].startswith("R001")
    # LLM extract 不应被调用
    assert extractor.calls == 0


def test_post_extraction_source_user_confirmed(db, test_user, client_with_extractor):
    """传 parsed_symptoms 时 symptom_observation.extraction_source='user_confirmed'。"""
    client, install = client_with_extractor
    install(_FakeExtractor(parsed=_high_fever_parsed()))

    body = _payload(test_user, idem_key=f"confirmed-{uuid4()}")
    body["parsed_symptoms"] = {
        "symptoms": [{"symptom_id": "fever", "numeric_value": 38.5}],
        "context": {"days_since_chemo": 3},
        "confidence": 1.0,
    }
    resp = client.post("/api/v1/assessments", json=body)
    assert resp.status_code == 201, resp.text

    db.commit()
    rows = db.execute(
        sa.text(
            "SELECT extraction_source FROM symptom_observation "
            "WHERE user_id = :uid"
        ),
        {"uid": test_user},
    ).mappings().all()
    assert len(rows) >= 1
    assert all(r["extraction_source"] == "user_confirmed" for r in rows)


def test_llm_extraction_error_returns_422_with_checklist_url(
    db, test_user, client_with_extractor
):
    """LLMExtractionError → 422 + ChecklistFallbackPrompt（reason / checklist_url / message）。"""
    client, install = client_with_extractor
    install(_FakeExtractor(error=LLMExtractionError("simulated low confidence")))

    resp = client.post("/api/v1/assessments", json=_payload(test_user))

    assert resp.status_code == 422
    detail = resp.json()["detail"]
    assert detail["reason"] == "low_confidence"
    assert detail["checklist_url"] == "/api/v1/checklist"
    assert "message" in detail

    # 没有 assessment 写入；也不应有 assessment_submitted 事件
    db.commit()
    n_assess = db.execute(
        sa.text("SELECT COUNT(*) FROM assessment WHERE user_id = :uid"),
        {"uid": test_user},
    ).scalar_one()
    assert n_assess == 0
    n_event = db.execute(
        sa.text(
            "SELECT COUNT(*) FROM event_log "
            "WHERE user_id = :uid AND event_type = 'assessment_submitted'"
        ),
        {"uid": test_user},
    ).scalar_one()
    assert n_event == 0
