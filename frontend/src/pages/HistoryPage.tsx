import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { listAssessments, AssessmentSummary } from "../api/client";

export default function HistoryPage() {
  const [items, setItems] = useState<AssessmentSummary[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    // TODO: 从登录态/Context 拿 user_id
    listAssessments("CURRENT_USER_ID")
      .then(setItems)
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <div>加载中...</div>;
  if (items.length === 0) return <div className="text-gray-500">还没有评估记录。</div>;

  return (
    <div className="space-y-2">
      <h1 className="text-xl font-semibold mb-4">历史记录</h1>
      {items.map((item) => (
        <Link
          key={item.assessment_id}
          to={`/result/${item.assessment_id}`}
          className="block p-3 bg-white border rounded-md hover:bg-gray-50"
        >
          <div className="flex justify-between text-sm">
            <span>{new Date(item.created_at).toLocaleString("zh-CN")}</span>
            <span className="font-medium">{item.risk_level}</span>
          </div>
          {item.primary_symptom && (
            <div className="text-xs text-gray-500 mt-1">{item.primary_symptom}</div>
          )}
        </Link>
      ))}
    </div>
  );
}
