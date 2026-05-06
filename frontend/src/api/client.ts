/**
 * API client —— 与 docs/api/openapi.yaml 保持一致
 *
 * 设计思路：先用最简的 fetch 包装；未来类型紧绷可以从 OpenAPI 生成 TS 类型
 * （openapi-typescript / orval 等工具）
 */

const BASE = "/api/v1";

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
      // TODO: 从登录态拿 user_id, session_id
      user_id: "CURRENT_USER_ID",
      session_id: "CURRENT_SESSION_ID",
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
