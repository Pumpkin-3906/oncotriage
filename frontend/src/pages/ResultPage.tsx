import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { analytics } from "../lib/analytics";
import { getAssessment, createContactRequest, AssessmentResult } from "../api/client";

const RISK_LABEL = {
  high: { text: "高风险", className: "bg-red-100 text-red-700" },
  medium: { text: "中风险", className: "bg-yellow-100 text-yellow-800" },
  low: { text: "低风险", className: "bg-green-100 text-green-700" },
} as const;

export default function ResultPage() {
  const { id } = useParams<{ id: string }>();
  const [data, setData] = useState<AssessmentResult | null>(null);

  useEffect(() => {
    if (!id) return;
    getAssessment(id).then((r) => {
      setData(r);
      analytics.emit("result_viewed", {
        assessment_id: id,
        risk_level: r.risk_level,
      });
    });
    return () => {
      analytics.emit("assessment_closed", { assessment_id: id });
    };
  }, [id]);

  async function handleContactTeam() {
    if (!data) return;
    analytics.emit("contact_team_clicked", { assessment_id: data.assessment_id });
    await createContactRequest({
      assessment_id: data.assessment_id,
      urgency: data.advice.urgency,
    });
    alert("已通知您的治疗团队");
  }

  if (!data) return <div>加载中...</div>;

  const riskStyle = RISK_LABEL[data.risk_level];

  return (
    <div className="space-y-6">
      <div className={`inline-block px-3 py-1 rounded-full text-sm font-medium ${riskStyle.className}`}>
        {riskStyle.text}
      </div>

      <div>
        <h2 className="font-semibold mb-2">建议</h2>
        <p className="whitespace-pre-line text-sm">{data.advice.text}</p>
      </div>

      {data.advice.contact_team && (
        <button
          onClick={handleContactTeam}
          className="w-full px-4 py-3 bg-blue-600 text-white rounded-md font-medium"
        >
          联系我的治疗团队
        </button>
      )}

      <details className="text-xs text-gray-500 border-t pt-4">
        <summary className="cursor-pointer">查看依据（审计）</summary>
        <div className="mt-2 space-y-2">
          {data.audit.matched_rules.map((r) => (
            <div key={r.rule_id}>
              <div className="font-mono">
                {r.rule_id} · v{r.rule_version}
              </div>
              <div>来源: {r.source_doc}</div>
              <div>{r.rationale_text}</div>
            </div>
          ))}
          <div>生成时间: {data.audit.generated_at}</div>
          <div>引擎版本: {data.audit.rule_engine_version}</div>
        </div>
      </details>
    </div>
  );
}
