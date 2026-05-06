-- ============================================================
-- 乳腺癌副作用智能体 MVP — 数据库 Schema (Canonical)
-- Version: 1.1.0
-- Last Updated: 2026-05-06
--
-- 设计原则:
--   1. 业务事实表（assessment / advice / evidence）和行为日志表（event_log）分离
--   2. 规则元数据（rule_source）独立存储，支持版本回溯审计
--   3. 同意管理（consent）作为所有数据出站的法律边界
--   4. 症状规范化（symptom_dictionary + symptom_observation），支持飞轮分析
--   5. 时序由 SQL 视图按需聚合，不维护快照缓存
--   6. 评估幂等键防止重复提交污染时序分析
--   7. case_review 表沉淀 bad cases，是 L3 学习闭环的入口
-- ============================================================


-- ── 用户 ─────────────────────────────────────────────────────
CREATE TABLE users (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    external_id     VARCHAR(64) UNIQUE NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- 临床上下文（影响规则触发，例如 days_since_chemo）
    diagnosis_code  VARCHAR(32),                    -- ICD-10, e.g. "C50.9"
    treatment_plan  VARCHAR(64),                    -- "AC-T", "TCHP" etc.
    last_chemo_at   TIMESTAMPTZ,
    is_active       BOOLEAN NOT NULL DEFAULT TRUE
);


-- ── 受控词表：症状字典 ───────────────────────────────────────
CREATE TABLE symptom_dictionary (
    id              VARCHAR(64) PRIMARY KEY,
    display_name_zh VARCHAR(128) NOT NULL,
    display_name_en VARCHAR(128) NOT NULL,
    ctcae_term      VARCHAR(128),
    ctcae_category  VARCHAR(64),
    aliases_zh      TEXT[],                         -- 患者口语别名，给 LLM grounding
    value_type      VARCHAR(16) NOT NULL,           -- 'numeric'|'categorical'|'binary'
    grading_scheme  VARCHAR(32) NOT NULL,           -- 'ctcae_v5'|'severity_3'|'binary'
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    added_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);


-- ── 业务事实层 (Layer 1 - PHI) ────────────────────────────────
CREATE TABLE assessment (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES users(id),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- 幂等键（前端生成 UUID，防重复提交污染时序分析）
    idempotency_key VARCHAR(64) NOT NULL,

    -- 输入
    raw_input_text  TEXT NOT NULL,
    input_source    VARCHAR(16) NOT NULL,           -- 'free_text'|'checklist_fallback'

    -- LLM 抽取原始输出（审计冻结，决策走 symptom_observation）
    parsed_symptoms JSONB,
    extraction_confidence    NUMERIC(3,2),
    extraction_model_version VARCHAR(64),

    -- 决策结果（可空 — Plan C 独立事务下，抽取已存但决策可能未完成）
    risk_level          VARCHAR(8),
    rule_engine_version VARCHAR(16),
    used_timeseries     BOOLEAN NOT NULL DEFAULT FALSE,

    -- 决策状态
    decision_status     VARCHAR(16) NOT NULL DEFAULT 'pending',
       -- 'pending' | 'completed' | 'failed'

    CONSTRAINT chk_risk CHECK (risk_level IS NULL OR risk_level IN ('high','medium','low')),
    CONSTRAINT chk_decision_status CHECK (decision_status IN ('pending','completed','failed'))
);
CREATE INDEX idx_assessment_user_time          ON assessment(user_id, created_at DESC);
CREATE UNIQUE INDEX idx_assessment_idempotency ON assessment(user_id, idempotency_key);


-- 症状观测：规范化的事实层
CREATE TABLE symptom_observation (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    assessment_id     UUID NOT NULL REFERENCES assessment(id) ON DELETE CASCADE,
    user_id           UUID NOT NULL REFERENCES users(id),       -- 冗余便于跨评估查询
    symptom_id        VARCHAR(64) NOT NULL REFERENCES symptom_dictionary(id),
    observed_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    numeric_value     NUMERIC(8,2),
    numeric_unit      VARCHAR(16),
    categorical_value VARCHAR(32),
    ctcae_grade       SMALLINT,
    duration_hours    NUMERIC(6,1),
    onset_at          TIMESTAMPTZ,
    interferes_with_adl BOOLEAN,

    extraction_source VARCHAR(16) NOT NULL,         -- 'llm'|'checklist'
    extraction_confidence NUMERIC(3,2),

    CONSTRAINT chk_grade CHECK (ctcae_grade BETWEEN 1 AND 5)
);
CREATE INDEX idx_symobs_user_time     ON symptom_observation(user_id, observed_at DESC);
CREATE INDEX idx_symobs_assessment    ON symptom_observation(assessment_id);
CREATE INDEX idx_symobs_symptom_time  ON symptom_observation(symptom_id, observed_at DESC);


-- 建议表
CREATE TABLE advice (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    assessment_id   UUID NOT NULL REFERENCES assessment(id) ON DELETE CASCADE,
    template_id     VARCHAR(64) NOT NULL,
    template_version VARCHAR(16) NOT NULL,
    rendered_text   TEXT NOT NULL,
    contact_team    BOOLEAN NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);


-- 证据表：审计核心
CREATE TABLE evidence (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    assessment_id   UUID NOT NULL REFERENCES assessment(id) ON DELETE CASCADE,
    rule_id         VARCHAR(64) NOT NULL,
    rule_version    VARCHAR(16) NOT NULL,
    matched_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    matched_fields  JSONB,                          -- 命中时的具体值
    rationale_text  TEXT NOT NULL                   -- 朴素 rationale，未来可换 RAG
);
CREATE INDEX idx_evidence_assessment ON evidence(assessment_id);
CREATE INDEX idx_evidence_rule       ON evidence(rule_id, rule_version);


-- 规则源：版本管理 + 完整 YAML 快照（审计冻结）
CREATE TABLE rule_source (
    rule_id         VARCHAR(64) NOT NULL,
    rule_version    VARCHAR(16) NOT NULL,
    source_doc      VARCHAR(128) NOT NULL,          -- 'CTCAE v5.0 §3.2'
    authored_by     VARCHAR(64) NOT NULL,
    reviewed_by     VARCHAR(64),
    effective_from  TIMESTAMPTZ NOT NULL,
    effective_until TIMESTAMPTZ,
    risk_level      VARCHAR(8) NOT NULL,
    rule_yaml       TEXT NOT NULL,
    PRIMARY KEY (rule_id, rule_version)
);


-- ── 协同请求（联系团队）─────────────────────────────────────
CREATE TABLE contact_request (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    assessment_id   UUID NOT NULL REFERENCES assessment(id),
    user_id         UUID NOT NULL REFERENCES users(id),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    urgency         VARCHAR(8) NOT NULL,            -- 'now_24h'|'this_week'|'next_visit'
    status          VARCHAR(16) NOT NULL DEFAULT 'pending',
    note_from_user  TEXT,
    handled_by      VARCHAR(64),
    handled_at      TIMESTAMPTZ
);


-- ── 行为日志层（与业务表正交） ────────────────────────────────
CREATE TABLE event_log (
    id              BIGSERIAL PRIMARY KEY,
    event_type      VARCHAR(64) NOT NULL,           -- 5 个核心事件之一
    user_id         UUID,
    session_id      VARCHAR(64) NOT NULL,
    assessment_id   UUID,
    occurred_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    payload         JSONB,
    client_info     JSONB
);
CREATE INDEX idx_event_user_time      ON event_log(user_id, occurred_at DESC);
CREATE INDEX idx_event_type_time      ON event_log(event_type, occurred_at DESC);
CREATE INDEX idx_event_assessment     ON event_log(assessment_id) WHERE assessment_id IS NOT NULL;


-- ── 同意层（数据飞轮的法律边界） ──────────────────────────────
CREATE TABLE consent (
    id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id               UUID NOT NULL REFERENCES users(id),
    scope                 VARCHAR(32) NOT NULL,
    data_recipient_class  VARCHAR(64) NOT NULL,
    purpose_text          TEXT NOT NULL,
    granted_at            TIMESTAMPTZ NOT NULL,
    revoked_at            TIMESTAMPTZ,
    expires_at            TIMESTAMPTZ,
    consent_version       VARCHAR(16) NOT NULL DEFAULT '1.0.0',

    CONSTRAINT chk_scope CHECK (scope IN (
        'clinical_care_only',
        'deidentified_research',
        'aggregated_industry',
        'regulatory_pv_reporting'
    ))
);
CREATE INDEX idx_consent_user_scope ON consent(user_id, scope) WHERE revoked_at IS NULL;


-- ── Bad Cases 审核：L3 学习闭环的入口 ─────────────────────────
-- 任何"系统输出可能有问题"的评估都流入这张表，由临床委员会定期 review，
-- 输出 → 改 rules.yaml / 改 prompt / 扩字典
CREATE TABLE case_review (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    assessment_id   UUID NOT NULL REFERENCES assessment(id),
    user_id         UUID NOT NULL REFERENCES users(id),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- 触发来源
    trigger_source  VARCHAR(32) NOT NULL,
       -- auto_low_confidence
       -- auto_extraction_failed
       -- auto_outcome_mismatch
       -- auto_repeat_high_no_action
       -- auto_default_rule_hit
       -- user_disagreement
       -- clinician_flag
    trigger_payload JSONB,                          -- 触发时的上下文快照

    -- 审核流转
    status          VARCHAR(16) NOT NULL DEFAULT 'pending',
       -- 'pending' | 'in_review' | 'resolved' | 'dismissed'
    reviewer_id     VARCHAR(64),
    reviewed_at     TIMESTAMPTZ,

    -- 审核结论
    verdict         VARCHAR(32),
       -- 'correct' | 'should_be_higher_risk' | 'should_be_lower_risk'
       -- | 'extraction_wrong' | 'rule_gap' | 'dictionary_gap'
    verdict_note    TEXT,

    -- 闭环动作（指向具体 PR / 配置变更）
    corrective_action JSONB,
       -- {"rule_pr": "...", "prompt_change": "v1.0.0->v1.0.1",
       --  "dictionary_added": ["fatigue_mental"]}

    CONSTRAINT chk_review_status CHECK (status IN ('pending','in_review','resolved','dismissed')),
    CONSTRAINT chk_trigger_source CHECK (trigger_source IN (
        'auto_low_confidence',
        'auto_extraction_failed',
        'auto_outcome_mismatch',
        'auto_repeat_high_no_action',
        'auto_default_rule_hit',
        'user_disagreement',
        'clinician_flag'
    ))
);
CREATE INDEX idx_case_review_status   ON case_review(status, created_at DESC);
CREATE INDEX idx_case_review_trigger  ON case_review(trigger_source, created_at DESC);


-- ── Advanced: 时序聚合视图（按需计算，无快照） ─────────────────
CREATE VIEW v_user_trend_7d AS
SELECT
    user_id,
    symptom_id,
    COUNT(*)                           AS observation_count,
    MAX(ctcae_grade)                   AS max_grade,
    MAX(numeric_value)                 AS max_numeric_value,
    CASE
        WHEN AVG(ctcae_grade) FILTER (WHERE observed_at > NOW() - INTERVAL '3 days')
           > AVG(ctcae_grade) FILTER (WHERE observed_at <= NOW() - INTERVAL '3 days')
        THEN 'increasing'
        WHEN AVG(ctcae_grade) FILTER (WHERE observed_at > NOW() - INTERVAL '3 days')
           < AVG(ctcae_grade) FILTER (WHERE observed_at <= NOW() - INTERVAL '3 days')
        THEN 'decreasing'
        ELSE 'stable'
    END                                AS trend
FROM symptom_observation
WHERE observed_at > NOW() - INTERVAL '7 days'
GROUP BY user_id, symptom_id;
