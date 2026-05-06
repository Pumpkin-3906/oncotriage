/**
 * API client —— 与 docs/api/openapi.yaml 保持一致
 *
 * 设计思路：先用最简的 fetch 包装；未来类型紧绷可以从 OpenAPI 生成 TS 类型
 * （openapi-typescript / orval 等工具）
 */

import type { ParsedSymptomsForm } from "../lib/symptom_dict";

const BASE = "/api/v1";

// ── MVP demo 身份（无登录）─────────────────────────────────
// 单次浏览器会话内固定 user_id；演示用，生产环境需走真实登录态
const DEMO_USER_KEY = "sz_demo_user_id";
const SESSION_KEY = "sz_session_id";

export function getDemoUserId(): string {
  let id = localStorage.getItem(DEMO_USER_KEY);
  if (!id) {
    // 演示用固定 UUID（与后端 DB 中已 INSERT 的 demo user 对应）
    id = "00000000-0000-0000-0000-000000000001";
    localStorage.setItem(DEMO_USER_KEY, id);
  }
  return id;
}

function getSessionId(): string {
  let id = sessionStorage.getItem(SESSION_KEY);
  if (!id) {
    id = crypto.randomUUID();
    sessionStorage.setItem(SESSION_KEY, id);
  }
  return id;
}

// ── 类型定义（与后端 schemas/assessment.py 对应）─────────────
export interface AssessmentResult {
  assessment_id: string;
  created_at: string;
  risk_level: "high" | "medium" | "low";
  advice: {
    text: string;
    contact_team: boolean;
    urgency: "now_24h" | "this_week" | "next_visit";
  };
  audit: {
    matched_rules: Array<{
      rule_id: string;
      rule_version: string;
      source_doc: string;
      matched_fields: Record<string, unknown>;
      rationale_text: string;
    }>;
    generated_at: string;
    rule_engine_version: string;
    extraction_model_version: string | null;
  };
  parsed_symptoms: unknown;
}

export interface AssessmentSummary {
  assessment_id: string;
  created_at: string;
  risk_level: string;
  primary_symptom: string | null;
}

// ── API 调用 ────────────────────────────────────────────────
export async function submitAssessment(input: {
  raw_input_text: string;
  idempotency_key?: string;  // 可选；不传则自动生成
}): Promise<AssessmentResult> {
  const idempotencyKey = input.idempotency_key ?? crypto.randomUUID();

  const res = await fetch(`${BASE}/assessments`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      // 后端读 header（也可放 body，二选一即可）
      "Idempotency-Key": idempotencyKey,
    },
    body: JSON.stringify({
      user_id: getDemoUserId(),
      session_id: getSessionId(),
      input_source: "free_text",
      idempotency_key: idempotencyKey,
      raw_input_text: input.raw_input_text,
    }),
  });
  if (!res.ok) throw new Error(`Submit failed: ${res.status}`);
  return res.json();
}

export async function getAssessment(id: string): Promise<AssessmentResult> {
  const res = await fetch(`${BASE}/assessments/${id}`);
  if (!res.ok) throw new Error(`Get failed: ${res.status}`);
  return res.json();
}

export async function listAssessments(
  userId: string
): Promise<AssessmentSummary[]> {
  const res = await fetch(`${BASE}/users/${userId}/assessments`);
  if (!res.ok) throw new Error(`List failed: ${res.status}`);
  const data = await res.json();
  return data.items ?? data;
}

// ── Extract（无状态预览，POST /assessments/extract）─────────
export interface MissingSlot {
  symptom_id: string;
  missing_fields: string[];
}

export interface CompletenessInfo {
  is_complete: boolean;
  missing_slots: MissingSlot[];
}

export interface ExtractResponse {
  parsed_symptoms: ParsedSymptomsForm;
  completeness: CompletenessInfo;
  extraction_model_version: string;
}

/** 后端 422 时携带 reason + message */
export class ExtractFailedError extends Error {
  reason: string;
  detail: string;
  constructor(reason: string, message: string) {
    super(message);
    this.name = "ExtractFailedError";
    this.reason = reason;
    this.detail = message;
  }
}

export interface ExtractInput {
  input_source: "free_text" | "checklist";
  raw_input_text?: string;
  form_payload?: ParsedSymptomsForm;
}

export async function extractAssessment(
  input: ExtractInput
): Promise<ExtractResponse> {
  const res = await fetch(`${BASE}/assessments/extract`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ user_id: getDemoUserId(), ...input }),
  });
  if (res.status === 422) {
    const detail = await res.json().catch(() => ({}));
    throw new ExtractFailedError(
      detail.reason ?? "extraction_failed",
      detail.message ?? "无法解析您的描述，建议改用清单模式"
    );
  }
  if (!res.ok) throw new Error(`Extract failed: ${res.status}`);
  return res.json();
}

export async function createContactRequest(payload: {
  assessment_id: string;
  urgency: string;
  note_from_user?: string;
}): Promise<{ contact_request_id: string }> {
  const res = await fetch(`${BASE}/contact-requests`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error(`Contact request failed: ${res.status}`);
  return res.json();
}
