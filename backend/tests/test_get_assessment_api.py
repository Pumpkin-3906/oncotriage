"""GET /api/v1/assessments/{id} 集成测试。

策略：先用 Orchestrator + FakeExtractor 写一条评估到真实库，再用 TestClient
调 GET 拿回完整 AssessmentResult；与 Orchestrator 测试共用 user fixture 思路。

覆盖任务卡 Part C 的 3 个必需 case + 一个 404 + 一个 pending 边界。
"""
from __future__ import annotations

import uuid
from uuid import uuid4

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient

from app.config import settings
from app.db import SessionLocal, get_db
from app.main import app
from app.models import Assessment
from app.rules.loader import load_rules
from app.schemas.assessment import (
    AssessmentRequest,
    ParsedSymptoms,
    SymptomItem,
)
from app.services.orchestrator import Orchestrator


# ── 测试 stubs / fixtures ────────────────────────────────────


class FakeExtractor:
    """复刻 test_orchestrator.py 中的 FakeExtractor —— 跳过真 LLM 调用。"""

    model = "fake-extractor-v1"

    def __init__(self, parsed: ParsedSymptoms):
        self._parsed = parsed
        self.calls = 0

    def extract(self, raw_text: str, dictionary: list[dict]) -> ParsedSymptoms:
        self.calls += 1
        return self._parsed


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def test_user(db):
    """临时 user，结束时级联清掉名下所有数据。"""
    user_id = uuid4()
    db.execute(
        sa.text("INSERT INTO users (id, external_id) VALUES (:id, :ext)"),
        {"id": user_id, "ext": f"get_assessment_test_{user_id}"},
    )
    db.commit()
    yield user_id
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


@pytest.fixture
def client(db):
    """TestClient，将 get_db 依赖覆盖到当前测试的 Session（共享事务可见性）。"""

    def _override():
        try:
            yield db
        finally:
            pass  # 由 db fixture 关闭

    app.dependency_overrides[get_db] = _override
    try:
        with TestClient(app) as c:
            yield c
    finally:
        app.dependency_overrides.pop(get_db, None)


def _high_fever_parsed() -> ParsedSymptoms:
    return ParsedSymptoms(
        symptoms=[SymptomItem(symptom_id="fever", numeric_value=38.5)],
        context={"days_since_chemo": 3},
        confidence=0.9,
    )


def _make_request(user_id: uuid.UUID) -> AssessmentRequest:
    return AssessmentRequest(
        user_id=user_id,
        session_id="test-session",
        input_source="free_text",
        idempotency_key=str(uuid4()),
        raw_input_text="化疗后发烧 38.5",
    )


def _seed_completed_assessment(db, user_id, rules_bundle):
    """工具：写一条 completed 状态的评估，返回 assessment_id。"""
    extractor = FakeExtractor(parsed=_high_fever_parsed())
    req = _make_request(user_id)
    result = Orchestrator(db, extractor=extractor, rules_bundle=rules_bundle).run(req)
    return result.assessment_id


# ── Cases ─────────────────────────────────────────────────────


def test_happy_path_post_then_get_returns_matched_rules(
    client, db, test_user, rules_bundle
):
    """Happy path：先写一条评估，GET 返回 200 + matched_rules 非空。"""
    assessment_id = _seed_completed_assessment(db, test_user, rules_bundle)

    resp = client.get(f"/api/v1/assessments/{assessment_id}")

    assert resp.status_code == 200
    body = resp.json()
    assert body["assessment_id"] == str(assessment_id)
    assert body["risk_level"] == "high"
    # matched_rules 非空 → 前端据此判定"评估成功"
    assert len(body["audit"]["matched_rules"]) >= 1
    assert body["audit"]["matched_rules"][0]["rule_id"].startswith("R001")


def test_get_unknown_id_returns_404(client):
    """ID 不存在 → 404。"""
    bogus = "00000000-0000-0000-0000-deadbeef0000"
    resp = client.get(f"/api/v1/assessments/{bogus}")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Assessment not found"


def test_get_full_audit_triple_all_non_null(
    client, db, test_user, rules_bundle
):
    """审计三件套 + 渲染三件套：matched_rules / generated_at / rule_engine_version
    + advice.text + parsed_symptoms 全部不为空。
    """
    assessment_id = _seed_completed_assessment(db, test_user, rules_bundle)

    resp = client.get(f"/api/v1/assessments/{assessment_id}")
    assert resp.status_code == 200
    body = resp.json()

    audit = body["audit"]
    # 审计三件套
    assert audit["matched_rules"], "matched_rules 不应为空"
    assert audit["generated_at"], "generated_at 不应为空"
    assert audit["rule_engine_version"], "rule_engine_version 不应为空"
    assert audit["rule_engine_version"] == rules_bundle.engine_version
    # 模型版本必须留存（来自 FakeExtractor.model）
    assert audit["extraction_model_version"] == "fake-extractor-v1"

    # 单条 matched_rule 字段齐全
    rule = audit["matched_rules"][0]
    assert rule["rule_id"]
    assert rule["rule_version"]
    assert rule["source_doc"], "source_doc 应反查 rules.yaml 取到（CTCAE/NCCN）"
    assert rule["matched_fields"], "matched_fields 应记录命中时的具体值"
    assert rule["rationale_text"], "rationale_text 不应为空"

    # 渲染层
    advice = body["advice"]
    assert advice["text"], "advice.text 不应为空"
    assert str(assessment_id) in advice["text"], "渲染时应嵌入 assessment_id"
    assert advice["contact_team"] is True
    assert advice["urgency"] == "now_24h"

    # parsed_symptoms 从 symptom_observation 反构 + context 来自 JSONB
    parsed = body["parsed_symptoms"]
    assert parsed["symptoms"], "parsed_symptoms.symptoms 不应为空"
    assert parsed["symptoms"][0]["symptom_id"] == "fever"
    assert parsed["symptoms"][0]["numeric_value"] == 38.5
    assert parsed["context"] == {"days_since_chemo": 3}


def test_get_invalid_uuid_returns_422(client):
    """格式错的 UUID → FastAPI 自动 422。"""
    resp = client.get("/api/v1/assessments/not-a-uuid")
    assert resp.status_code == 422


def test_get_pending_assessment_returns_200_with_empty_matched_rules(
    client, db, test_user
):
    """评估处于 pending 状态（仅 Tx1 完成）→ 200，matched_rules 为空。

    模拟：直接插一条 decision_status='pending' 的 assessment（无 evidence/advice）。
    """
    pending = Assessment(
        user_id=test_user,
        idempotency_key=f"pending-{uuid4()}",
        raw_input_text="未跑规则",
        input_source="free_text",
        parsed_symptoms={"symptoms": [], "context": {}, "confidence": None},
        extraction_model_version="fake-extractor-v1",
        used_timeseries=False,
        decision_status="pending",
    )
    db.add(pending)
    db.commit()
    db.refresh(pending)

    resp = client.get(f"/api/v1/assessments/{pending.id}")
    assert resp.status_code == 200
    body = resp.json()

    # 前端约定：matched_rules 空表示评估未完成
    assert body["audit"]["matched_rules"] == []
    # advice 退化为空文本（无渲染）
    assert body["advice"]["text"] == ""
    assert body["advice"]["contact_team"] is False
