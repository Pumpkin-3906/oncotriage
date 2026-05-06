import { useState } from "react";
import { useNavigate } from "react-router-dom";

/**
 * 3 步引导。完成后写 localStorage('sz_onboarded') 跳过下次。
 *
 * 触发：
 * - 首次进入：App.tsx 的 RootRedirect 检测无标记 → 跳到 /onboarding
 * - 顶部 ? 按钮：用户主动重看（不重置标记）
 *
 * 跳过 / 完成都会写标记 + navigate('/')。
 */
export default function OnboardingPage() {
  const [step, setStep] = useState<1 | 2 | 3>(1);
  const [agreed, setAgreed] = useState(false);
  const navigate = useNavigate();

  function finish() {
    localStorage.setItem("sz_onboarded", new Date().toISOString());
    navigate("/");
  }

  return (
    <div className="space-y-6">
      <ProgressDots step={step} />

      {step === 1 && <Step1 />}
      {step === 2 && <Step2 />}
      {step === 3 && (
        <Step3 agreed={agreed} setAgreed={setAgreed} />
      )}

      <div className="flex justify-between pt-2">
        {step === 1 ? (
          <button
            onClick={finish}
            className="text-gray-500 text-sm hover:underline"
          >
            跳过
          </button>
        ) : (
          <button
            onClick={() => setStep((s) => (s - 1) as 1 | 2 | 3)}
            className="text-gray-600 text-sm hover:underline"
          >
            ← 返回
          </button>
        )}

        {step < 3 ? (
          <button
            onClick={() => setStep((s) => (s + 1) as 1 | 2 | 3)}
            className="px-4 py-2 bg-blue-600 text-white rounded-md text-sm"
          >
            继续 →
          </button>
        ) : (
          <button
            onClick={finish}
            disabled={!agreed}
            className="px-4 py-2 bg-blue-600 text-white rounded-md text-sm disabled:bg-gray-300"
          >
            我同意，开始 →
          </button>
        )}
      </div>
    </div>
  );
}

function ProgressDots({ step }: { step: 1 | 2 | 3 }) {
  return (
    <div className="flex justify-center gap-2 pt-2" aria-label={`第 ${step} 步 / 共 3 步`}>
      {[1, 2, 3].map((n) => (
        <span
          key={n}
          className={
            "w-2 h-2 rounded-full " +
            (n === step ? "bg-blue-600" : "bg-gray-300")
          }
        />
      ))}
    </div>
  );
}

function Step1() {
  return (
    <div className="space-y-4 text-center">
      <h1 className="text-2xl font-semibold">🩺 OncoTriage</h1>
      <p className="text-gray-700">
        帮您评估化疗副作用的风险等级
        <br />
        并给出下一步建议
      </p>
      <div className="bg-yellow-50 border border-yellow-200 rounded-md p-4 text-left text-sm space-y-1">
        <div className="font-medium">⚠️ 重要说明</div>
        <ul className="list-disc list-inside text-gray-700 space-y-1">
          <li>不替代医生诊断</li>
          <li>紧急情况请直接拨打 120</li>
          <li>您的数据加密保存</li>
        </ul>
      </div>
    </div>
  );
}

function Step2() {
  return (
    <div className="space-y-4">
      <h2 className="text-lg font-semibold">您可以这样告诉我们您的症状：</h2>

      <div className="border rounded-md p-4 space-y-1">
        <div className="font-medium">📝 自然语言</div>
        <p className="text-sm text-gray-600">像跟医生说话一样描述</p>
        <p className="text-sm text-gray-500 italic">
          "化疗第三天发烧 38.5 度"
        </p>
        <p className="text-sm text-gray-600">也可以 🎤 语音输入（v2 启用）</p>
      </div>

      <div className="border rounded-md p-4 space-y-1">
        <div className="font-medium">☑️ 勾选症状清单</div>
        <p className="text-sm text-gray-600">不知道怎么描述时使用</p>
        <p className="text-sm text-gray-600">从 12 类常见症状中选择</p>
      </div>
    </div>
  );
}

function Step3({
  agreed,
  setAgreed,
}: {
  agreed: boolean;
  setAgreed: (v: boolean) => void;
}) {
  return (
    <div className="space-y-4">
      <h2 className="text-lg font-semibold">您的数据如何被使用：</h2>

      <div className="space-y-3">
        <div className="bg-green-50 border border-green-200 rounded-md p-4">
          <div className="font-medium text-green-800 mb-1">✓ 我们会：</div>
          <ul className="list-disc list-inside text-sm text-gray-700 space-y-1">
            <li>加密保存您的症状记录</li>
            <li>紧急情况通知您的治疗团队</li>
          </ul>
        </div>

        <div className="bg-red-50 border border-red-200 rounded-md p-4">
          <div className="font-medium text-red-800 mb-1">✗ 我们不会：</div>
          <ul className="list-disc list-inside text-sm text-gray-700 space-y-1">
            <li>在未授权时共享数据</li>
            <li>把您的描述卖给第三方</li>
          </ul>
        </div>
      </div>

      <p className="text-sm">
        详细说明 →{" "}
        <a href="#" className="text-blue-600 hover:underline">
          隐私政策
        </a>
      </p>

      <label className="flex items-start gap-2 text-sm cursor-pointer select-none">
        <input
          type="checkbox"
          checked={agreed}
          onChange={(e) => setAgreed(e.target.checked)}
          className="mt-0.5"
        />
        <span>我已阅读并同意上述数据使用方式</span>
      </label>
    </div>
  );
}
