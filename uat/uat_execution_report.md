# UAT Execution Report (UI + API)

Date: 2026-02-15
Scope: 覆盖前端 UI 涉及功能点（Student + Teacher），并对关键 API 做黑盒断言。

## Legend
- √ = 符合预期
- ✗ = 不符合预期（需定位→修复→回归）
- (note) = 备注/执行细节

---

## A. Student UI

### A1 登录
- √ 正向：Student_01/1234 登录成功进入驾驶舱
- √ 负向：会话被教师释放后，学生端显示「当前会话被终止」并强制登出到登录页（登录页显示 info 文案）

### A2 Round 状态与关闭
- √ Round Active：Round 2 显示 🟢 OPEN、Remaining 5/5
- √ Round STOP：教师 STOP 后学生端显示「当前轮次已结束」，并禁用 SUBMIT STRATEGY / CSV 提交

### A3 CSV 上传提交
- √ 正向：上传合法 finish CSV（来自 finish 数据抽取）可提交并得到结果
- √ 负向（预期=400）：缺 now_pos 列 → 400（API runner 覆盖）
- √ 负向（预期=400）：缺弯道（turn12）→ 400（API runner 覆盖）

### A4 History
- √ 历史记录显示包含 DNF 与 finish（不因 DNF 过滤）
- √ History 显示 Round/Attempt 信息与圈速/DNF 文案

### A5 Download CSV
- √ DNF 仍可下载过程数据：DNF 时 Lap Time 显示 DNF，Download CSV 按钮仍为 active 可点击

---

## B. Teacher UI

### B1 登录
- √ teacher_01/1234 登录成功进入 Race Control

### B2 Driver Monitor
- √ 表格渲染（状态/Driver/Attempts/Best Lap/操作）
- √ Student 01 行显示 Attempts（例：1/5）与 Best Lap（无有效圈速时显示 -）

### B3 释放登录态（Release Session）
- √ 点击 Student 01「释放登录态」后，学生端强制登出并提示「当前会话被终止」

### B4 STOP SESSION
- √ 触发 STOP 后：round.is_active=0（DB 验证），学生端显示「当前轮次已结束」
- note: UI 自动化执行 STOP 时需预置 `window.confirm=() => true` 才能稳定触发 axios 请求。

---

## C. API Runner（黑盒断言）
- √ N1 invalid login → 401
- √ N2 submit-csv without auth → 401
- √ N3 missing now_pos → 400 (A)
- √ N4 missing corner(turn12) → 400 (A)
- √ P1 submit-csv finish → 200 + is_dnf=false + final_time>0
- √ P3 teacher/dashboard 可访问且 students 列表非空

---

## Issues Found
- None remaining in this run (all executed cases matched expected).
