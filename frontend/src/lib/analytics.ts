/**
 * 5 个核心事件埋点 —— 对应 DESIGN.md §9
 *
 * 策略 A+C:
 *   - 普通事件: fetch + keepalive (fire-and-forget)
 *   - assessment_closed: navigator.sendBeacon (关页面也能发出去)
 *
 * 幂等：业务层（POST /assessments）用 Idempotency-Key 防重复，
 *       事件层用 event_id (UUID) 让后端可去重，但 MVP 不强制。
 */

export type EventType =
  | "assessment_started"
  | "assessment_submitted"
  | "result_viewed"
  | "contact_team_clicked"
  | "assessment_closed"
  // MVP+3：confirm 页生命周期
  | "confirm_page_viewed"
  | "extraction_confirmed";

interface EventRecord {
  event_id: string;       // 客户端生成 UUID，后端可用于去重
  event_type: EventType;
  occurred_at: string;
  session_id: string;
  payload: Record<string, unknown>;
}

const SESSION_KEY = "sz_session_id";
const EVENTS_ENDPOINT = "/api/v1/events";

function getSessionId(): string {
  let id = sessionStorage.getItem(SESSION_KEY);
  if (!id) {
    id = crypto.randomUUID();
    sessionStorage.setItem(SESSION_KEY, id);
  }
  return id;
}

class Analytics {
  emit(event: EventType, payload: Record<string, unknown> = {}): void {
    const record: EventRecord = {
      event_id: crypto.randomUUID(),
      event_type: event,
      occurred_at: new Date().toISOString(),
      session_id: getSessionId(),
      payload,
    };

    const body = JSON.stringify(record);

    // assessment_closed: 用 sendBeacon，关页面/导航走也能发出
    if (event === "assessment_closed" && navigator.sendBeacon) {
      const blob = new Blob([body], { type: "application/json" });
      navigator.sendBeacon(EVENTS_ENDPOINT, blob);
    } else {
      // 其他事件: fetch + keepalive (fire-and-forget)
      fetch(EVENTS_ENDPOINT, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body,
        keepalive: true,
      }).catch((err) => {
        // A 策略：失败丢弃（埋点缺失不能影响主流程）
        console.warn("[analytics] failed:", event, err);
      });
    }

    if (import.meta.env.DEV) {
      console.log("[event]", event, payload);
    }
  }
}

export const analytics = new Analytics();
