"""POST /api/v1/assessments/extract 集成测试 —— 无状态预览。

覆盖任务卡 4 个必需 case：
  1. free_text → 调 LLM 抽取，返 parsed_symptoms + completeness
  2. checklist → 直接用 form_payload 构造 ParsedSymptoms，不调 LLM
  3. LLM 抛 LLMExtractionError → 422 + reason='extraction_failed'
  4. extract 不写任何业务表
"""
from __future__ import annotations

from uuid import uuid4

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient

from app.api import assessments as assessments_module
from app.db import SessionLocal, get_db
from app.main import app
from app.schemas.assessment import ParsedSymptoms, SymptomItem
from app.services.llm_extractor import LLMExtractionError


# ── Stubs ────────────────────────────────────────────────────


class _FakeExtractor:
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
    user_id = uuid4()
    db.execute(
        sa.text("INSERT INTO users (id, external_id) VALUES (:id, :ext)"),
        {"id": user_id, "ext": f"extract_test_{user_id}"},
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
def client_with_extractor(db, monkeypatch):
    """注入 FakeExtractor 替换 _build_extractor，并 override get_db."""
    state: dict = {"extractor": None}

    def fake_build_extractor():
        return state["extractor"]

    monkeypatch.setattr(assessments_module, "_build_extractor", fake_build_extractor)
    app.dependency_overrides[get_db] = lambda: db

    def install(extractor):
        state["extractor"] = extractor

    try:
        with TestClient(app) as c:
            yield c, install
    finally:
        app.dependency_overrides.pop(get_db, None)


# ── Cases ────────────────────────────────────────────────────


def test_extract_free_text_returns_parsed_and_completeness(
    db, test_user, client_with_extractor
):
    """free_text 模式：调 LLM 抽取，返 parsed_symptoms + completeness + model_version。"""
    client, install = client_with_extractor
    parsed = ParsedSymptoms(
        symptoms=[SymptomItem(symptom_id="fever", numeric_value=None)],
        context={},
        confidence=0.7,
    )
    extractor = _FakeExtractor(parsed=parsed)
    install(extractor)

    resp = client.post(
        "/api/v1/assessments/extract",
        json={
            "user_id": str(test_user),
            "input_source": "free_text",
            "raw_input_text": "我发烧了",
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert extractor.calls == 1
    assert data["parsed_symptoms"]["symptoms"][0]["symptom_id"] == "fever"
    assert data["parsed_symptoms"]["symptoms"][0]["numeric_value"] is None
    # fever value_type=numeric，缺 numeric_value → incomplete
    assert data["completeness"]["is_complete"] is False
    missing = data["completeness"]["missing_slots"]
    assert any(
        m["symptom_id"] == "fever" and "numeric_value" in m["missing_fields"]
        for m in missing
    )
    assert data["extraction_model_version"] == "fake-extractor-v1"


def test_extract_checklist_skips_llm(db, test_user, client_with_extractor):
    """checklist 模式：直接 model_validate(form_payload)，不调 LLM。"""
    client, install = client_with_extractor
    extractor = _FakeExtractor(parsed=ParsedSymptoms(symptoms=[]))  # 不应被调用
    install(extractor)

    form_payload = {
        "symptoms": [{"symptom_id": "fever", "numeric_value": 38.5}],
        "context": {"days_since_chemo": 3},
        "confidence": 1.0,
    }
    resp = client.post(
        "/api/v1/assessments/extract",
        json={
            "user_id": str(test_user),
            "input_source": "checklist",
            "form_payload": form_payload,
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert extractor.calls == 0  # checklist 不调 LLM
    assert data["parsed_symptoms"]["symptoms"][0]["numeric_value"] == 38.5
    assert data["parsed_symptoms"]["context"]["days_since_chemo"] == 3
    assert data["completeness"]["is_complete"] is True


def test_extract_llm_failure_returns_422_with_reason(
    db, test_user, client_with_extractor
):
    """LLMExtractionError → 422 + detail.reason='extraction_failed'。"""
    client, install = client_with_extractor
    install(_FakeExtractor(error=LLMExtractionError("simulated")))

    resp = client.post(
        "/api/v1/assessments/extract",
        json={
            "user_id": str(test_user),
            "input_source": "free_text",
            "raw_input_text": "blah",
        },
    )
    assert resp.status_code == 422
    detail = resp.json()["detail"]
    assert detail["reason"] == "extraction_failed"
    assert "message" in detail


def test_extract_does_not_write_db(db, test_user, client_with_extractor):
    """extract 不写任何业务表（assessment / observation / evidence / event_log）。"""
    client, install = client_with_extractor
    install(_FakeExtractor(parsed=ParsedSymptoms(
        symptoms=[SymptomItem(symptom_id="fever", numeric_value=38.5)],
        context={"days_since_chemo": 3},
        confidence=0.9,
    )))

    resp = client.post(
        "/api/v1/assessments/extract",
        json={
            "user_id": str(test_user),
            "input_source": "free_text",
            "raw_input_text": "发烧 38.5 度",
        },
    )
    assert resp.status_code == 200

    db.commit()
    for table in ("assessment", "symptom_observation", "event_log"):
        n = db.execute(
            sa.text(f"SELECT COUNT(*) FROM {table} WHERE user_id = :uid"),
            {"uid": test_user},
        ).scalar_one()
        assert n == 0, f"extract should not write {table}"
