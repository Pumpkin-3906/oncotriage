"""GET /api/v1/users/{user_id}/assessments 集成测试。

覆盖任务卡 4 个必需 case：
  1. 返回该用户的 assessment 列表（按 created_at desc）
  2. 未知 user → items=[] (200)
  3. primary_symptom 从 evidence.matched_fields 反查首个 symptom_<id>_<field> 的 id
  4. 兜底规则 R999 → primary_symptom=null
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient

from app.db import SessionLocal, get_db
from app.main import app
from app.models import Assessment, Evidence


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
        {"id": user_id, "ext": f"history_test_{user_id}"},
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
def client(db):
    app.dependency_overrides[get_db] = lambda: db
    try:
        with TestClient(app) as c:
            yield c
    finally:
        app.dependency_overrides.pop(get_db, None)


def _insert_assessment(
    db,
    user_id,
    *,
    risk_level: str = "high",
    created_at: datetime | None = None,
    idem_suffix: str = "x",
) -> Assessment:
    a = Assessment(
        user_id=user_id,
        idempotency_key=f"hist-{idem_suffix}-{uuid4()}",
        raw_input_text="dummy",
        input_source="free_text",
        parsed_symptoms={"symptoms": [], "context": {}},
        risk_level=risk_level,
        rule_engine_version="v1.0",
        used_timeseries=False,
        decision_status="completed",
    )
    db.add(a)
    db.flush()
    if created_at is not None:
        # 直接 update created_at 列（默认 server_default=now()）
        db.execute(
            sa.text("UPDATE assessment SET created_at=:t WHERE id=:id"),
            {"t": created_at, "id": a.id},
        )
    db.commit()
    db.refresh(a)
    return a


def _insert_evidence(
    db,
    assessment_id,
    *,
    rule_id: str,
    matched_fields: dict,
    rationale: str = "matched",
):
    db.add(Evidence(
        assessment_id=assessment_id,
        rule_id=rule_id,
        rule_version="1.0.0",
        matched_fields=matched_fields,
        rationale_text=rationale,
    ))
    db.commit()


# ── Cases ────────────────────────────────────────────────────


def test_list_assessments_returns_user_history_desc(db, test_user, client):
    """3 条 assessment 按 created_at desc 返回。"""
    now = datetime.now(timezone.utc)
    a_old = _insert_assessment(
        db, test_user, created_at=now - timedelta(days=2), idem_suffix="old"
    )
    a_mid = _insert_assessment(
        db, test_user, created_at=now - timedelta(days=1), idem_suffix="mid"
    )
    a_new = _insert_assessment(
        db, test_user, created_at=now, idem_suffix="new"
    )

    resp = client.get(f"/api/v1/users/{test_user}/assessments")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["next_cursor"] is None
    items = body["items"]
    assert len(items) == 3
    ids = [i["assessment_id"] for i in items]
    assert ids == [str(a_new.id), str(a_mid.id), str(a_old.id)]
    # 字段齐全
    assert items[0]["risk_level"] == "high"
    assert "created_at" in items[0]
    assert "primary_symptom" in items[0]


def test_list_assessments_unknown_user_returns_empty(client):
    """未知 user_id → 200 + items=[]"""
    unknown = uuid4()
    resp = client.get(f"/api/v1/users/{unknown}/assessments")
    assert resp.status_code == 200
    body = resp.json()
    assert body["items"] == []
    assert body["next_cursor"] is None


def test_list_assessments_primary_symptom_from_evidence(db, test_user, client):
    """primary_symptom 取首条 evidence 的 matched_fields 中 symptom_<id>_<field> 的 id。"""
    a = _insert_assessment(db, test_user, idem_suffix="ps1")
    _insert_evidence(
        db,
        a.id,
        rule_id="R001",
        matched_fields={
            "symptom_fever_numeric_value": 38.5,
            "context_days_since_chemo": 3,
        },
    )

    resp = client.get(f"/api/v1/users/{test_user}/assessments")
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert len(items) == 1
    assert items[0]["primary_symptom"] == "fever"


def test_list_assessments_default_rule_primary_symptom_is_null(
    db, test_user, client
):
    """兜底规则 R999 → primary_symptom=null"""
    a = _insert_assessment(db, test_user, risk_level="low", idem_suffix="r999")
    _insert_evidence(
        db,
        a.id,
        rule_id="R999",
        matched_fields={"reason": "no_match_default"},
        rationale="default fallback",
    )

    resp = client.get(f"/api/v1/users/{test_user}/assessments")
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert len(items) == 1
    assert items[0]["primary_symptom"] is None
