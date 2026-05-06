import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { analytics } from "../lib/analytics";
import { submitAssessment } from "../api/client";

export default function InputPage() {
  const [text, setText] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const navigate = useNavigate();

  // 一次进入页面 = 一个 idempotency_key
  // 即使用户连点 100 次提交，后端也只会处理一次
  const idempotencyKeyRef = useRef<string>(crypto.randomUUID());

  useEffect(() => {
    analytics.emit("assessment_started");
  }, []);

  async function handleSubmit() {
    if (!text.trim() || submitting) return;
    setSubmitting(true);
    analytics.emit("assessment_submitted", { input_length: text.length });

    try {
      const result = await submitAssessment({
        raw_input_text: text,
        idempotency_key: idempotencyKeyRef.current,
      });
      navigate(`/result/${result.assessment_id}`);
    } catch (err) {
      // TODO: 处理 422 → 展示 checklist 兜底
      console.error(err);
      setSubmitting(false);
    }
  }

  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold">描述您的不适</h1>
      <p className="text-sm text-gray-600">
        请尽量详细地描述症状，包括出现时间、严重程度、是否影响日常活动等。
      </p>
      <textarea
        value={text}
        onChange={(e) => setText(e.target.value)}
        rows={8}
        maxLength={4000}
        placeholder="例：昨天打完化疗第三天，今天下午开始发烧 38.5 度，浑身发冷..."
        className="w-full p-3 border rounded-md text-sm"
      />
      <button
        onClick={handleSubmit}
        disabled={submitting || !text.trim()}
        className="px-4 py-2 bg-blue-600 text-white rounded-md disabled:bg-gray-300"
      >
        {submitting ? "评估中..." : "提交评估"}
      </button>
    </div>
  );
}
