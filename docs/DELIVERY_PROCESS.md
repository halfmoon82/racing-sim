# Delivery Process (PRD → Dev → Test → UAT → Release)

> 目标：让每次迭代都可复用、可追溯、可验收，减少“做对功能但做错语义”。

## 0) Vocabulary（统一术语）

### Smoke Test（冒烟）
- 目的：确认系统“能跑、关键链路不崩”。
- 特点：快、覆盖窄、发现阻断级问题。

### SAT（System/Service Acceptance Test，系统验收测试）
- 目的：确认系统作为整体按设计工作（接口契约、模块协同、稳定性、边界条件）。
- 特点：黑盒为主 + 契约断言（HTTP code、字段、语义不变量）。

### UAT（User Acceptance Test，用户验收测试）
- 目的：确认用户从前端完成任务，看到的结果符合 PRD 业务语义。
- 特点：以“前端输入/前端展示”定义预期，提供证据链（截图/返回体/数据）。

---

## 1) PRD 语义冻结（必须先做）
输出一页 **Acceptance Semantics**，所有后续用例/实现以此为准。

模板（必须回答）：
1. **统计口径**：例如 Best Lap 是否仅当前轮次？History 是否跨轮次？
2. **错误语义映射**：例如 Session terminated vs Round ended 的 UI 文案/行为。
3. **DNF 处理**：DNF 是否允许下载 telemetry？DNF 是否上榜？
4. **输入校验规则**：输入不合法是否 400（强校验）还是允许提交后 DNF？
5. **可恢复路径**：例如 Cockpit Occupied 的解除方式。

> 这一步属于“语义分岔点”，必须与 Owner（Sir）确认后再写代码。

---

## 2) 用例先行（Test Plan First）

### 2.1 Smoke 用例（5~10 条）
- login ok / login fail
- submit ok（至少一条 finish）
- teacher dashboard ok
- DB 写回基本完整（result_data 非空；finish 必须 result_time 非空）

### 2.2 SAT 用例（契约 + 不变量）
- 错误码一致（401/403/400）
- Finish/DNF 不变量：
  - DNF ⇒ is_dnf=true 且 final_time/result_time 为 NULL
  - Finish ⇒ is_dnf=false 且 final_time/result_time 为 number
- 排行榜/Best Lap 口径一致：仅统计 is_dnf=0 且 result_time 非空
- 并发/重试：不会错读策略/不会写错 job/不会产生“空壳完成”

### 2.3 UAT 用例（按 UI 功能点）
每个 UI 功能点至少：
- 1 条正向（Happy path）
- 1 条负向（Bad input / bad state）

用例必须写清：
- 前端输入（点击、上传 CSV、填写字段）
- 预期接口返回（status code + schema）
- 预期 UI 展示（文案、按钮状态、排序结果、下载可用性）

---

## 3) 实现策略（Vertical Slice）
优先做“端到端闭环”的最小切片：
1. UI 输入 → API → DB 写回 → UI 可见结果
2. 再扩展功能点（排序、历史下载、teacher summary 等）

强约束：
- 任何“禁区/硬规则”（例如物理引擎不可改）必须作为最高优先级。

---

## 4) 自动化与证据

### 4.1 API Runner
- 断言：状态码、字段、语义不变量、跨端一致性。
- 改动后必须回归跑一遍。

### 4.2 UI Checklist（黑盒）
- 用浏览器真实操作验证关键 UI 语义。
- 需要的证据：页面截图/aria snapshot/关键文本。

### 4.3 UAT 报告格式
- 用例编号
- 预期 vs 实际
- √ / ✗
- 证据（截图路径、返回体片段、DB 旁证）

---

## 5) 版本管理（必须执行）

### 5.1 Commit 规则
- `feat:` 新功能
- `fix:` bug 修复
- `uat:` 测试资产/runner/报告
- `chore:` 工程维护（gitignore、脚本整理）

### 5.2 Tag（阶段性交付）
- 每次“可以验收/可回滚”的节点打 tag：
  - `vYYYY.MM.DD-<topic>`

### 5.3 Workspace Hygiene
- DB/log/tmp 不进 git（用 `.gitignore`）
- UAT 输入样本（CSV/脚本）入 repo（可复现）

---

## 6) 何时必须向 Sir 确认 vs 可自主推进

### 必须确认（语义分岔点）
- 统计口径：best lap 是否跨轮次、history 是否过滤
- 关键文案/行为：STOP 后提示语、会话失效是否强制登出
- 输入校验策略：400 vs 容错后 DNF
- 破坏性操作：清库/reset/stop round 等
- 硬约束：例如物理引擎不可改

### 可自主推进（细节实现）
- 不改变语义的 UI 增强（排序、按钮、布局）
- 明确的契约修复（字段对齐、NULL 过滤）
- 测试资产沉淀（runner、脚本、报告模板、tag）

---

## Appendix: Racing-sim 实践要点（沉淀）
- Cockpit Occupied：清理 redis `user_session:<id>` + sessions 表对应 user 的 is_active。
- Teacher STOP SESSION：学生端语义为「当前轮次已结束」。
- Teacher release-session：学生端语义为「当前会话被终止」并强制登出。
- DNF 仍允许下载 telemetry（raw_data）。
