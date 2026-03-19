# PRD 差异清单（第三轮）

## 已覆盖
- [x] 三角色鉴权（Admin/Teacher/Student）
- [x] Admin localhost 限制
- [x] Teacher 4终端并发登录限制
- [x] Student 首入原则（单终端）
- [x] 5-run 仿真择优
- [x] Job UUID 隔离目录
- [x] 提交配额锁（事务）
- [x] Teacher 轮次创建/停止
- [x] Teacher 导出轮次最佳成绩 CSV
- [x] Student 手动录入提交
- [x] Student CSV 上传提交
- [x] FIFO 30 条 + Golden Record 保护

## 需继续完善（第四轮建议）
- [ ] 提交动画“Run 1/5”实时进度（当前为最终返回）
- [ ] Stop Session 对进行中任务的强制中断机制（当前同步执行）
- [ ] Round 自动截止计时器前后端联动
- [ ] 更完整的错误码映射与中英双语 Toast 文案统一
- [ ] 弯道顺序的“严格缺失检查”提示（当前是顺序检查）
- [ ] Admin Teacher CRUD 完整（当前 C/R 为主）
- [ ] 前端历史记录真实数据渲染（当前框架已留位）

## 验收建议
1. 先跑 scripts/e2e_smoke_test.py 验证基础链路
2. 再做并发提交压测（同一学生2请求竞争）
3. 最后做 UI 交互验收与文案校对
