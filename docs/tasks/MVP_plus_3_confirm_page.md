# Task MVP+3 — 前端 ConfirmExtractionPage

> 独立任务卡。
> 与 MVP+2 / MVP+4 并行；与 MVP+2 在症状字典 mirror 上有重叠（共用 `symptom_dict.ts`），
> 假设 MVP+2 已经/会创建该文件。如果你先动手，把它建好（MVP+2 review 时合并差异）。

## 目标

按 `docs/UX_DESIGN.md` §2.3 实现 ConfirmExtractionPage —— 用户审阅 + 编辑 LLM
抽取结果 + 补充缺失字段，确认后 POST 走规则引擎决策。

## 必读

1. `docs/UX_DESIGN.md` §2.3 (ConfirmExtractionPage)、§3 (API 契约)、§6 (UX 决策)
2. `frontend/src/pages/ResultPage.tsx`（参考其 styling 风格）
3. `frontend/src/api/client.ts`（要扩展）
4. `backend/app/rules/seed_dictionary.py`（symptom_dict 内容来源）

## 范围

### Part A — ConfirmExtractionPage

新建 `frontend/src/pages/ConfirmExtractionPage.tsx`，路由 `/confirm`。

#### 入参

通过 `react-router-dom` 的 `useLocation().state` 接收：

```ts
interface ConfirmState {
  extraction: ExtractResponse;       // 来自 InputPage 调 extract 返回
  raw_input_text: string;
  input_source: 'free_text' | 'checklist';
}
```

如果 `state` 为空（用户直接访问 /confirm），重定向到 `/`。

#### 状态管理

```ts
const [parsedSymptoms, setParsedSymptoms] = useState<ParsedSymptoms>(extraction.parsed_symptoms);
const [completenessLocal, setCompletenessLocal] = useState(extraction.completeness);
// 用户编辑后 completeness 要重新算（前端做，简单查表，不需要再调 API）
```

#### UI 结构（按 §2.3）

```
┌─ 顶部回显原始输入 ────────────────┐
│ 您说："化疗第3天发烧了，恶心"        │
└──────────────────────────────────┘

┌─ Incomplete Banner（条件显示）──────┐
│ ⚠️ 您的描述缺少 N 项关键信息         │
│ 请补充以便给出准确判断                │
└──────────────────────────────────┘

我们这样理解您的描述：

📌 距离上次化疗：[3] 天 [可改]   <- 编辑 context.days_since_chemo

每个 symptom 一张卡片：
┌─ 🌡️ 发热              [✕] ─┐
│  ⚠️ 体温：[___] °C *必填    │  <- 缺必填红色边框
│  持续时间：[__] 小时 选填   │
└────────────────────────────┘

[+ 补充其他症状] (展开列出未抽到的 12-N 个)

┌─ 操作 ──────────────────────────┐
│ [← 重新描述]   [确认 看结果 →]   │  <- 缺必填时第二个 disabled
└──────────────────────────────┘
```

#### 关键交互

1. **删除症状**：点击 `[✕]` 直接从 `parsedSymptoms.symptoms` 移除
2. **编辑字段**：直接在 input/radio 上改，更新 state，重算 completeness
3. **添加症状**：从未在 list 里的 `SYMPTOMS` 中选，加默认空字段
4. **本地重算 completeness**：用 `symptom_dict.ts` 的逻辑（mirror CompletenessChecker）：
   ```ts
   function recomputeCompleteness(parsed: ParsedSymptoms): CompletenessInfo {
     const missing: MissingSlot[] = [];
     for (const sym of parsed.symptoms) {
       const spec = symptomById(sym.symptom_id);
       if (!spec) { missing.push({ symptom_id: sym.symptom_id, missing_fields: ['unknown_symptom'] }); continue; }
       if (spec.value_type === 'numeric' && sym.numeric_value == null) missing.push({...});
       if (spec.value_type === 'categorical' && sym.ctcae_grade == null && sym.categorical_value == null) missing.push({...});
     }
     return { is_complete: missing.length === 0, missing_slots: missing };
   }
   ```
5. **"重新描述"**：`navigate('/')` 同时把原 raw_input_text 通过 state 传回（让 InputPage 预填）
6. **"确认看结果"**：调 POST /assessments 传 confirmed parsed_symptoms

```ts
async function handleConfirm() {
  if (!completenessLocal.is_complete) return;  // disabled 状态下点不到
  
  analytics.emit('extraction_confirmed', { 
    edited_count: countEdits(extraction.parsed_symptoms, parsedSymptoms),
  });
  
  const result = await submitAssessment({
    raw_input_text,
    parsed_symptoms: parsedSymptoms,
  });
  navigate(`/result/${result.assessment_id}`);
}
```

### Part B — API client 扩展

修改 `frontend/src/api/client.ts` 中的 `submitAssessment` 接受可选 `parsed_symptoms`：

```ts
export async function submitAssessment(input: {
  raw_input_text: string;
  idempotency_key?: string;
  parsed_symptoms?: ParsedSymptoms;   // 新增
}): Promise<AssessmentResult> {
  const idempotencyKey = input.idempotency_key ?? crypto.randomUUID();
  const res = await fetch(`${BASE}/assessments`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'Idempotency-Key': idempotencyKey },
    body: JSON.stringify({
      user_id: getDemoUserId(),
      session_id: getSessionId(),
      input_source: 'free_text',  // confirmation 后保留原 source
      idempotency_key: idempotencyKey,
      raw_input_text: input.raw_input_text,
      parsed_symptoms: input.parsed_symptoms,
    }),
  });
  if (!res.ok) throw new Error(`Submit failed: ${res.status}`);
  return res.json();
}
```

注意确保 `ParsedSymptoms` 类型在 client.ts 里已定义或 export 出来。

### Part C — symptom_dict.ts 共享

如果 MVP+2 已建好这个文件（`frontend/src/lib/symptom_dict.ts`），直接 import 用。
如果你先动手：建一个最小版本含 12 条 SYMPTOMS + 必要工具函数，并在你的 PR body 注明
"如与 MVP+2 冲突，以本文件为准 / 合并以 MVP+2 为准"。

### Part D — App.tsx 路由

加新路由：

```tsx
<Route path="/confirm" element={<ConfirmExtractionPage />} />
```

### Part E — 测试（轻量）

由于 MVP 阶段不写前端组件测试（见 MVP_PLAN.md），本任务仅需：
- 手工测试：在 Confirm 页编辑字段后 completeness banner 实时变化
- TS typecheck 通过

如果你愿意写一个简单的 vitest 验证 `recomputeCompleteness()` 函数，加分但非必需。

## 不要做的

- ❌ 不要去主仓干活（你的 worktree: `/Users/pumpkin/projects/oncotriage-mvp3`）
- ❌ 不要碰后端代码
- ❌ 不要碰 InputPage / OnboardingPage / ChecklistInput（MVP+2 范围）
- ❌ 不要碰 HistoryPage（MVP+4 范围）
- ❌ 不要 push（本地 commit 即可）
- ❌ 不要装新依赖
- ❌ 不要实现"添加自定义未在字典里的症状" — 只允许从 12 条里选

## Definition of Done

```
[ ] ConfirmExtractionPage 实现，含编辑 / 删除 / 添加症状
[ ] Incomplete banner 条件显示
[ ] 缺必填时"确认"按钮 disabled
[ ] 本地 recomputeCompleteness 工具函数（mirror 后端 checker）
[ ] api/client.ts submitAssessment 接受 parsed_symptoms 入参
[ ] App.tsx 加 /confirm 路由
[ ] 类型导出 ParsedSymptoms / SymptomItem 给页面用
[ ] tsc --noEmit 0 错误
[ ] 总改动 LOC ≤ 600
```

## 验收（手工）

```bash
cd /Users/pumpkin/projects/oncotriage-mvp3/frontend
npm install --silent
npx tsc --noEmit

npm run dev
# 浏览器手工流程：
# 1. 走完 onboarding → InputPage（如 MVP+2 已就绪）
# 2. 输入 "我发烧了" → 提交 → 跳到 /confirm
# 3. 顶部应有 incomplete banner
# 4. fever 卡片应有红色"温度 *必填"
# 5. "确认" 按钮 disabled
# 6. 填入 38.5 → banner 消失 → "确认" enabled
# 7. 点击确认 → 跳到 ResultPage 显示 high risk + R001
```

如果 MVP+1 / MVP+2 还没合入 main，可以用 mock 数据手工注入 ConfirmState 测试。

## 提交规范

- **PR 标题**：`[MVP+3] frontend: confirm extraction page with editable fields`
- **Commit 数**：1-2

## 设计提示

- 用 react-router 的 `useLocation().state` 传 ConfirmState（避免序列化进 URL）
- 编辑事件用受控组件（每次 onChange 更 state）；性能可接受（≤12 个 symptom）
- "添加其他症状"按钮点击展开一个 popup/inline list，展示未在 parsed.symptoms 里的字典条目
- 如果 input_source='checklist'（用户已经在 ChecklistInput 填得很全），confirm 页应该 90% 字段都已填，banner 不显示直接 enabled
