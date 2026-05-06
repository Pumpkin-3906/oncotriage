# Task MVP+2 — 前端 InputPage + Onboarding + ChecklistInput

> 独立任务卡。
> 可与 MVP+3 / MVP+4 并行（不强依赖 MVP+1，但你的页面要按 §3 API 契约写）。

## 目标

按 `docs/UX_DESIGN.md` §2.1 + §2.2 实现：
1. **3 步 Onboarding** —— 首次访问展示，含隐私同意
2. **InputPage** mode toggle —— 自然语言（默认）+ 勾选清单
3. **ChecklistInput** 组件 —— 12 类症状按字典动态生成字段
4. **症状字典 mirror** —— 前端 hardcode 12 条字典（display_name + 字段类型）

## 必读

1. `docs/UX_DESIGN.md` §2.1 (Onboarding)、§2.2 (InputPage)、§6 (UX 决策)
2. `backend/app/rules/seed_dictionary.py` —— 12 条字典源数据
3. `frontend/src/pages/InputPage.tsx` —— 现有，要重写
4. `frontend/src/api/client.ts` —— 现有 client（你要加 extract API 调用）
5. `frontend/src/App.tsx` —— 路由配置

## 范围

### Part A — Onboarding 3 步

新建 `frontend/src/pages/OnboardingPage.tsx`：

```tsx
// 路由 /onboarding
// 状态：currentStep 1-3
// 完成时 localStorage.setItem('sz_onboarded', new Date().toISOString())
// 跳过：直接 setItem 跳到 InputPage
```

**3 步内容**严格按 `UX_DESIGN.md §2.1`：
- Step 1：欢迎 + 重要说明（不替代医生 / 紧急拨 120 / 数据加密）
- Step 2：两种输入方式说明
- Step 3：隐私同意 + "我同意，开始"

#### App.tsx 路由调整

新增逻辑：
```tsx
function RootRedirect() {
  const onboarded = localStorage.getItem('sz_onboarded');
  return onboarded ? <InputPage /> : <Navigate to="/onboarding" />;
}

<Route path="/" element={<RootRedirect />} />
<Route path="/onboarding" element={<OnboardingPage />} />
```

顶部导航加 `?` 图标（不影响 onboarded 状态，仅再次展示 onboarding）。

### Part B — Symptom Dictionary Mirror

新建 `frontend/src/lib/symptom_dict.ts`：

```typescript
export type ValueType = 'numeric' | 'categorical';
export type GradingScheme = 'ctcae_v5' | 'severity_3' | 'binary';

export interface SymptomSpec {
  id: string;
  display_name_zh: string;
  display_name_en: string;
  category: 'urgent' | 'chemo_common' | 'endocrine' | 'other';  // 新增 UI 分组
  value_type: ValueType;
  grading_scheme: GradingScheme;
  unit?: string;  // numeric 时显示
}

export const SYMPTOMS: SymptomSpec[] = [
  // 紧急（5）
  { id: 'fever', display_name_zh: '发热', category: 'urgent', value_type: 'numeric', grading_scheme: 'ctcae_v5', unit: '°C', ... },
  { id: 'shortness_of_breath', ..., category: 'urgent', value_type: 'categorical', grading_scheme: 'ctcae_v5' },
  { id: 'severe_chest_pain', ..., category: 'urgent', value_type: 'categorical', grading_scheme: 'severity_3' },
  { id: 'severe_diarrhea', ..., category: 'urgent', value_type: 'categorical', grading_scheme: 'ctcae_v5' },
  // ... 完整 12 条对照 backend/app/rules/seed_dictionary.py 的 SYMPTOMS
];

// 工具函数
export function symptomById(id: string): SymptomSpec | undefined { ... }
export function fieldLabel(field: string): string {
  // numeric_value -> "数值"; ctcae_grade -> "严重程度 (CTCAE 1-5)"; categorical_value -> "严重程度"
}
```

### Part C — InputPage 重写

`frontend/src/pages/InputPage.tsx`：

```tsx
const [mode, setMode] = useState<'free_text' | 'checklist'>('free_text');
const [text, setText] = useState('');
const [formData, setFormData] = useState<ParsedSymptomsForm>({...});

async function handleSubmit() {
  analytics.emit('assessment_submitted', { mode });
  
  // MVP+ 流程：先 extract 预览，跳到 ConfirmExtractionPage
  const extractRes = await extractAssessment(
    mode === 'free_text'
      ? { input_source: 'free_text', raw_input_text: text }
      : { input_source: 'checklist', form_payload: formData }
  );
  
  // 路由到 confirm 页，state 传递抽取结果
  navigate('/confirm', { state: { 
    extraction: extractRes, 
    raw_input_text: text,
    input_source: mode,
  }});
}
```

UI 结构按 `UX_DESIGN.md §2.2`：
- mode toggle (segmented control)
- 自然语言：textarea + 字数计数 + 🎤 按钮（**MVP+ 阶段先做按钮 disabled + tooltip "v2 启用"**，不做语音真实接入）
- 清单：渲染 `<ChecklistInput formData={formData} onChange={setFormData} />`

### Part D — ChecklistInput 组件

新建 `frontend/src/components/ChecklistInput.tsx`：

```tsx
interface ChecklistInputProps {
  value: ParsedSymptomsForm;
  onChange: (next: ParsedSymptomsForm) => void;
}
```

按 `UX_DESIGN.md §2.2 清单 mode`：
- 顶部：化疗第几天 number input + "未化疗" 复选框（互斥）
- 三个分组（按 SymptomSpec.category）：紧急 / 化疗常见 / 内分泌相关
- 每个症状：checkbox + 勾选后展开字段
  - numeric (fever) → number input + 单位
  - categorical (ctcae_v5) → 3 选 1 radio (G1/G2/G3) + "影响日常活动" toggle
  - categorical (severity_3) → 3 选 1 radio (mild/moderate/severe)

输出符合 ParsedSymptoms schema：
```ts
{
  symptoms: [{ symptom_id, numeric_value?, ctcae_grade?, categorical_value?, interferes_with_adl? }],
  context: { days_since_chemo: number | null }
}
```

### Part E — API client 扩展

`frontend/src/api/client.ts` 新增：

```ts
export async function extractAssessment(input: {
  input_source: 'free_text' | 'checklist';
  raw_input_text?: string;
  form_payload?: object;
}): Promise<ExtractResponse> {
  const res = await fetch(`${BASE}/assessments/extract`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ user_id: getDemoUserId(), ...input }),
  });
  if (res.status === 422) {
    const detail = await res.json();
    throw new ExtractFailedError(detail.reason, detail.message);
  }
  if (!res.ok) throw new Error(`Extract failed: ${res.status}`);
  return res.json();
}

// 类型
export interface ExtractResponse {
  parsed_symptoms: ParsedSymptoms;
  completeness: { is_complete: boolean; missing_slots: Array<{ symptom_id: string; missing_fields: string[] }> };
  extraction_model_version: string;
}
```

## 不要做的

- ❌ 不要去主仓干活（你的 worktree: `/Users/pumpkin/projects/oncotriage-mvp2`）
- ❌ 不要碰后端代码（那是 MVP+1 的事）
- ❌ 不要碰 `pages/ConfirmExtractionPage.tsx`（那是 MVP+3 的事）
- ❌ 不要碰 `pages/HistoryPage.tsx` / 历史相关（那是 MVP+4 的事）
- ❌ 不要 push（本地 commit 即可）
- ❌ 不要装新 npm 依赖（只用现有的 react / tailwind / react-router）
- ❌ 不要做语音输入真实接入（按钮 disabled 即可，v2 再做）
- ❌ 不要做隐私政策页（onboarding step 3 的"详细说明"链接先指向 #）

## Definition of Done

```
[ ] OnboardingPage 3 步实现 + localStorage 持久化
[ ] App.tsx 路由调整：/ 根据 onboarded 状态分发
[ ] symptom_dict.ts 12 条对照 seed_dictionary.py
[ ] InputPage 重写含 mode toggle
[ ] ChecklistInput 组件完整（按 value_type 动态字段）
[ ] api/client.ts 加 extractAssessment
[ ] tsc --noEmit 0 错误
[ ] 手工测试：刷浏览器 → onboarding → input page 两种 mode 都能填 → 控制台 console.log 提交内容正确
[ ] 总改动 LOC ≤ 800（包括新文件）
```

## 验收

```bash
cd /Users/pumpkin/projects/oncotriage-mvp2/frontend
npm install --silent
npx tsc --noEmit && echo "✓ typecheck pass"

# 启动 dev server
npm run dev
# 浏览器 http://localhost:5173 应该自动跳到 /onboarding
# 走完 3 步 → 跳到 InputPage
# 切换 mode → 看两种输入方式
# 自然语言：键入文本，提交（不需要 backend 跑通也能 console.log 出 payload）
# 清单：勾选 fever → 展开温度输入 → 勾选 nausea → 展开 grade radio
```

## 提交规范

- **PR 标题**：`[MVP+2] frontend: onboarding + input page mode toggle + checklist`
- **Commit 数**：3-4（onboarding / dict mirror / input page / checklist component）

## 设计提示

- ChecklistInput 用 useReducer 管 formData，每个症状的字段更新走 dispatch
- 按 category 分组用简单 array.filter；不要做 collapse / accordion（MVP 简单为先）
- mode toggle 用 Tailwind 自带样式 + radio inputs（不引 UI lib）
- onboarding 的 progress dots (●○○) 可以用 emoji 或简单 div
