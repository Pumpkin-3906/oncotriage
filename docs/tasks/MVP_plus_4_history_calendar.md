# Task MVP+4 — 前端 HistoryPage 日历视图

> 独立任务卡。
> 与 MVP+1 / MVP+2 / MVP+3 并行。需要 MVP+1 的 `GET /users/{id}/assessments` 接口。
> 你可以先用 mock 数据开发，等 MVP+1 合入后联调。

## 目标

按 `docs/UX_DESIGN.md` §2.4 重做 HistoryPage：从平铺列表 → 日历主视图，
每天用风险色圆点标注，点击展开当日列表。

## 必读

1. `docs/UX_DESIGN.md` §2.4 (HistoryPage)
2. `frontend/src/pages/HistoryPage.tsx`（现有，要重写）
3. `frontend/src/api/client.ts` 中的 `listAssessments()` 和 `AssessmentSummary` 类型

## 范围

### Part A — 重写 HistoryPage

`frontend/src/pages/HistoryPage.tsx`：

#### 状态

```ts
const [items, setItems] = useState<AssessmentSummary[]>([]);
const [loading, setLoading] = useState(true);
const [currentMonth, setCurrentMonth] = useState(new Date());  // 当前显示月份
const [selectedDate, setSelectedDate] = useState<string | null>(null);  // ISO date 字符串
```

#### 数据加载

`listAssessments()` 一次拉所有（MVP 量小，不分页）。

#### UI 三区

##### 1. 概览栏（顶部）

```tsx
const stats = useMemo(() => {
  return {
    total: items.length,
    high: items.filter(i => i.risk_level === 'high').length,
    medium: items.filter(i => i.risk_level === 'medium').length,
    low: items.filter(i => i.risk_level === 'low').length,
    weeklyAvg: calculateWeeklyAverage(items),
  };
}, [items]);
```

显示：`共评估 23 次 · 高风险 4 · 中 9 · 低 10` + `最近一周：每天平均 1.4 次`

##### 2. 日历网格

按 `currentMonth` 渲染整月（包含上下月 padding 的灰色日期）：

```tsx
const monthGrid = useMemo(() => buildMonthGrid(currentMonth), [currentMonth]);
const itemsByDate = useMemo(() => groupByDate(items), [items]);
```

每天 cell：
- 日期数字
- 该日 risk dots：最多 3 个；> 3 时显示 `+N`
- dot 颜色：`high → red-500` / `medium → amber-500` / `low → green-500`
- 今天的 cell 加 ring/border 高亮

```tsx
<div className="grid grid-cols-7 gap-1">
  {['日','一','二','三','四','五','六'].map(d => (
    <div key={d} className="text-xs text-center text-gray-500 py-1">{d}</div>
  ))}
  {monthGrid.map(day => {
    const dateKey = formatDate(day);
    const dayItems = itemsByDate[dateKey] || [];
    const isToday = isSameDay(day, new Date());
    const isCurrentMonth = day.getMonth() === currentMonth.getMonth();
    return (
      <button
        key={dateKey}
        onClick={() => setSelectedDate(dateKey)}
        className={`p-2 rounded-lg ${isToday ? 'ring-2 ring-blue-500' : ''} 
                    ${isCurrentMonth ? '' : 'text-gray-300'}
                    ${dayItems.length > 0 ? 'hover:bg-gray-100' : ''}`}
      >
        <div className="text-sm">{day.getDate()}</div>
        <div className="flex justify-center gap-0.5 mt-0.5 h-2">
          {dayItems.slice(0, 3).map((item, i) => (
            <span key={i} className={`w-1.5 h-1.5 rounded-full ${dotColor(item.risk_level)}`} />
          ))}
          {dayItems.length > 3 && (
            <span className="text-xs text-gray-500">+{dayItems.length - 3}</span>
          )}
        </div>
      </button>
    );
  })}
</div>
```

月份导航：`[<] 2026 年 5 月 [今天] [>]`

##### 3. 选中日期展开列表

`selectedDate !== null` 时在日历下方显示：

```tsx
<div className="mt-4 p-3 bg-white border rounded-lg">
  <h3>{formatChineseDate(selectedDate)}</h3>
  <ul>
    {itemsByDate[selectedDate]?.map(item => (
      <Link key={item.assessment_id} to={`/result/${item.assessment_id}`}>
        <li className="py-2 border-b last:border-0">
          <span>{formatTime(item.created_at)}</span>
          <span className={`ml-2 px-2 py-0.5 rounded text-xs ${riskBadgeStyle(item.risk_level)}`}>
            {riskLabel(item.risk_level)}
          </span>
          {item.primary_symptom && (
            <span className="ml-2 text-sm text-gray-600">{primarySymptomLabel(item.primary_symptom)}</span>
          )}
        </li>
      </Link>
    ))}
  </ul>
</div>
```

### Part B — 工具函数

新建 `frontend/src/lib/calendar.ts`：

```ts
export function buildMonthGrid(month: Date): Date[] {
  // 返回从月初所在那个周日 → 月底所在那个周六的 6×7 = 42 天数组
  // (确保始终 6 行整齐)
}

export function groupByDate<T extends {created_at: string}>(items: T[]): Record<string, T[]> {
  // 按 ISO date (YYYY-MM-DD) 分组
}

export function formatDate(d: Date): string { ... }  // YYYY-MM-DD
export function formatTime(iso: string): string { ... }  // HH:mm
export function formatChineseDate(iso: string): string { ... }  // 5 月 13 日，星期三
export function isSameDay(a: Date, b: Date): boolean { ... }
export function calculateWeeklyAverage(items: Array<{created_at: string}>): number {
  // 最近 7 天的每天平均评估次数
}
```

### Part C — 空状态

`items.length === 0` 时不展示日历，显示：

```tsx
<div className="text-center py-12 text-gray-500">
  <div className="text-5xl mb-3">📋</div>
  <p>还没有评估记录</p>
  <Link to="/" className="inline-block mt-3 px-4 py-2 bg-blue-600 text-white rounded">
    开始第一次评估
  </Link>
</div>
```

### Part D — Risk badge styling 复用

如果 ResultPage 已经定义了 risk colors，新建 `frontend/src/lib/risk.ts`：

```ts
export const RISK_LABEL: Record<string, string> = { 
  high: '高风险', medium: '中风险', low: '低风险' 
};
export function dotColor(risk: string): string {
  return { high: 'bg-red-500', medium: 'bg-amber-500', low: 'bg-green-500' }[risk] ?? 'bg-gray-400';
}
export function riskBadgeStyle(risk: string): string { ... }
```

让 ResultPage 也用此 lib（如果方便），保持一致性。

### Part E — 联调

依赖 MVP+1 实现的 `GET /users/{user_id}/assessments`。

如果 MVP+1 还没合入 main，**先用 mock 数据开发**：

```ts
// 临时 mock
async function listAssessments(_userId: string): Promise<AssessmentSummary[]> {
  if (import.meta.env.DEV && false /* set true to use mock */) {
    return [
      { assessment_id: '1', created_at: '2026-05-07T14:23:00Z', risk_level: 'high', primary_symptom: 'fever' },
      // ... more mock items
    ];
  }
  // 真实 API
  const res = await fetch(`${BASE}/users/${userId}/assessments`);
  // ...
}
```

PR body 里说明 mock 是否被启用。

## 不要做的

- ❌ 不要去主仓干活（worktree: `/Users/pumpkin/projects/oncotriage-mvp4`）
- ❌ 不要碰后端代码
- ❌ 不要碰 InputPage / OnboardingPage / ConfirmExtractionPage
- ❌ 不要 push（本地 commit 即可）
- ❌ 不要装新依赖（特别是 `react-day-picker` / `date-fns` / `dayjs` 等 —— 自写日历）
- ❌ 不要做趋势折线图（v2 范围）
- ❌ 不要做日历的拖拽 / 多选

## Definition of Done

```
[ ] HistoryPage 日历视图完整（月份导航 + 风险色点 + 今日高亮 + 选中展开）
[ ] 概览栏统计正确
[ ] 工具函数 calendar.ts 单独文件
[ ] 空状态 UI
[ ] tsc --noEmit 0 错误
[ ] 真实 API（MVP+1 完成后）或 mock 数据下手工跑通
[ ] 总改动 LOC ≤ 500
```

## 验收

```bash
cd /Users/pumpkin/projects/oncotriage-mvp4/frontend
npm install --silent
npx tsc --noEmit

npm run dev
# 浏览器：
# 1. 进 /history（点导航 "历史"）
# 2. 应看到当前月份日历（无数据时显示空状态）
# 3. （联调时）点击有 dot 的日期 → 下方展开当日 assessment 列表
# 4. 点击列表项 → 跳到 ResultPage
# 5. [<] [>] 切换月份正常
# 6. [今天] 跳回当月
```

## 提交规范

- **PR 标题**：`[MVP+4] frontend: history page calendar view with risk dots`
- **Commit 数**：2-3（calendar utils / risk lib / history page rewrite）

## 设计提示

- 月份网格固定 42 格（6 行 × 7 列）—— 即使 28 天的 2 月也填满，避免 layout shift
- 使用原生 `Date` API + 简单工具函数，不要引日期库
- 概览栏的"最近一周"用 `items.filter(i => new Date(i.created_at) > sevenDaysAgo)`
- 移动端可见性：每个 day cell ≥ 44pt 触控目标
