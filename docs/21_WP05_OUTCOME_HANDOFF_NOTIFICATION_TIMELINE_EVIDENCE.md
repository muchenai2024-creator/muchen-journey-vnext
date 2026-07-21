# 21｜WP-05 结果、交接、通知与历史构建证据

状态：`AS_BUILT`  
版本：V0.1  
日期：2026-07-21  
验证环境：本地 Docker Compose，未部署  
Owner：Liu Mowen（初始 Product + Tech Owner）

## 1. 结论与证据边界

本工作包在本地批准范围内关闭 `REQ-BR-007`、`REQ-BR-009`、`REQ-BR-010`：评审 `APPROVE` 后原子生成不可变 Outcome、唯一 Handoff、最小化 Outbox 事件和本地 NotificationDelivery；真实 worker 进程覆盖 claim、成功、失败、退避重试、最终失败、并发、租约恢复和去重；Learner 结果页展示最终人工结论、结构化反馈、交接、通知事实与跨域时间线。

结论是 `WP-05 LOCAL BUILD VERIFIED`。这只代表本地代码、迁移、合同、自动化、Compose、HTTP 与真实浏览器证据通过；不代表真实通知送达、真人 UAT、发布 GO 或生产就绪。

真实 Feishu、邮件、AI、staging/production、物理 ACL、备份恢复和发布签署均没有运行，详见第 9 节。

## 2. 开工 Gap Audit

开工前完整读取 README、00、03、04、05、06、07、08、09 V0.2、10 V0.2、11、12、13、14、15、16、17、18、19、20，并对照批准决策、状态机、API/事件、安全和测试合同。WP-04 根任务独立基线为 38 passed；其最小 `Outcome(HANDOFF_READY)`、`outcome.created` 和通用 Outbox 只用于 walking-skeleton 回归，不能视为 WP-05 完成。

| 批准要求 | 开工时事实 | WP-05 As-Built | 主要证据 |
| --- | --- | --- | --- |
| 最终结果与交接 | Outcome 只有 enrollment/evaluation/status/自由文本 next_step；没有收件人/Assignment 固定 scope、不可变 trigger 或独立交接事实 | Outcome 固定 organization/learner/assignment/enrollment/evaluation；Handoff 独立拥有唯一 `CONFIRM_HANDOFF` 下一步；两者 DB 不可变 | `0008_outcome_notifications`；不可变负向测试 |
| 原子与只产生一次 | APPROVE 直接插入最小 Outcome；没有完整 bundle 或 replay 计数证明 | Evaluation→Outcome→Handoff→三条 scoped Outbox→Delivery 在一个事务中按依赖顺序 flush、一次 commit；唯一约束、幂等 replay 与并发 finalize 保证一次 | bundle count=(1,1,3,1)；WP-04 并发回归；WP-05 replay 测试 |
| 通知生命周期 | worker 只把通用 Outbox 标成 processed；没有 attempt、lease、backoff、delivery 或 dedupe | Outbox `PENDING/PROCESSING/SENT/FAILED`；Delivery `PENDING/SENDING/DELIVERED/RETRY_WAIT/DEAD`；append-only Attempt；LocalReceipt 去重；指数退避和租约恢复 | 三组真实 worker 子进程测试 |
| 外部失败降级 | 没有故障注入或结果独立性证明 | `fail_once`、`always_fail`、adapter commit 后 crash 均已注入；Outcome/Evaluation/Handoff 不变，结果页仍正确；AI 明确 `NOT_ENABLED` | retry/dead/crash 测试；最终页面 |
| 完整结果页 | 只显示 status/decision/feedback/next_step | 显示最终人工结论、总体与四维反馈、交接责任人/唯一下一步、通知状态/本地范围、AI 未启用和不可变时间线 | Next production build；真实 Playwright |
| 跨域时间线 | 只有各页面局部历史；无 result timeline | `GET /me/timeline` 组合 SubmissionVersion、Review/Evaluation、Outcome/Handoff、通知请求与 append-only attempts；游标分页 | scope/GET purity/cursor API 测试 |
| 授权与最小化 | 旧通用事件没有 organization/owner；payload 为 aggregate ID | result/timeline 同时约束 role、organization、owner 和对象链；通知 event/delivery 使用复合 scope FK；payload 不含称呼、正文或反馈；日志不含资源 ID/PII | 0009 hardening；同组织其他 owner 负向测试；日志扫描 |
| Worker 管理边界 | 无完整通知管理合同 | 没有管理 API 可任意改 status；状态只由原子 bundle 和 worker 状态机推进；production 拒绝 LOCAL_TEST adapter | OpenAPI 断言；production fail-closed 子进程 |

`muchen-journey-ops:operate-muchen-journey` 按要求先执行。技能 doctor 返回 `Not a compatible Muchen Journey repository`；没有创建第二套脚本，后续沿用仓库既有 Make、Compose、curl 和 Playwright，并如实保留这一债务。

## 3. 实际实现合同

### 3.1 Outcome、Handoff 与原子 finalize

- `APPROVE` 继续把 Evaluation 持久结论映射为 `PASS`，Assignment/Enrollment 进入 `COMPLETED`；`REQUEST_REVISION` 仍只进入 `NEEDS_REVISION`，不生成 Outcome/Handoff/通知。
- Outcome 固定 `organization_id`、`learner_id`、`assignment_id`、`enrollment_id` 与 `source_evaluation_id`，状态只能是 `HANDOFF_READY`。复合外键同时证明 Enrollment owner 和 Evaluation/Assignment scope。
- Handoff 固定同一 Outcome/Enrollment/Evaluation、同组织 owner，状态只能是 `READY`，`next_step_code` 只能是 `CONFIRM_HANDOFF`；Outcome、Enrollment、Evaluation 均是一对一唯一，所以唯一 next step 只产生一次。
- 数据库 trigger 拒绝 Outcome/Handoff 的任何 UPDATE/DELETE；结果页只做读取投影，不复制生成第二条交接事实。
- finalize 中的 staged flush 只确定复合外键写入顺序，仍处于同一数据库事务；任何一步失败都由最终 commit 一起回滚。

### 3.2 Outbox、worker 与 NotificationDelivery

| 阶段 | Outbox | Delivery | 追加事实 |
| --- | --- | --- | --- |
| 原子请求 | `PENDING`, attempt=0, next=now | `PENDING`, attempt=0 | 最小 `notification.requested.v1` |
| claim | `PROCESSING`, lock/token, attempt+1 | `SENDING`, attempt 同步 | 无 |
| 本地成功 | `SENT`, processed_at | `DELIVERED`, delivered_at | `NotificationAttempt(DELIVERED)` + 唯一 LocalReceipt |
| 可重试失败 | `FAILED`, next_attempt_at | `RETRY_WAIT`, next/error | `FAILED_RETRYABLE` |
| 最终失败 | `FAILED`, next=NULL | `DEAD`, next=NULL/error | `FAILED_FINAL` |
| 租约过期恢复 | 新 claim、attempt+1 | `SENDING` | 旧 attempt 追加 `LEASE_EXPIRED`；已有 Receipt 时不再调用投递副作用 |

- worker 使用 `FOR UPDATE SKIP LOCKED` 竞争 due event；外部/本地 adapter 在 claim 事务之外执行，成功或失败通过 lock token 条件完成，失去租约的旧 worker 不能覆盖新状态。
- `OUTBOX_LEASE_SECONDS` 和 `WORKER_POLL_SECONDS` 下限均为 1，防止 0 秒租约立即偷取仍在处理的事件或 0 秒空转。
- dedupe key 固定 Outcome、recipient、channel、template version；LocalReceipt 在独立事务内唯一提交。已投递后进程崩溃时，恢复 worker 看到 Receipt 直接完成，不生成第二份收据。
- 两个真实 worker 进程同时竞争同一事件时只有一个 `processed=1`，最终 attempt=1、Receipt=1、Attempt=1。
- worker 日志只记录 event type、attempt、final/deduplicated 与 error code；不记录收件人、称呼、正文、反馈、Outcome/Evaluation/event ID。
- Compose 只配置 `LOCAL_TEST` adapter。`APP_ENV` 为 staging/production 时该 adapter fail closed；没有 Feishu/Email/AI client、credential 或网络调用。

### 3.3 通知失败不污染核心结果

- Outcome/Handoff 在 Reviewer finalize 事务内完成；通知消费是后续独立 worker 事务。worker 的 adapter 失败不能回滚、更新或删除 Evaluation/Outcome/Handoff。
- `fail_once` 第一轮得到 `FAILED/RETRY_WAIT`，第二轮成功为 `SENT/DELIVERED`；结果的 Evaluation/Handoff 投影前后完全一致。
- `always_fail` 达到 max attempts 后为 `FAILED/DEAD`；Learner 结果仍为 `PASS`，且页面明确“核心结果不依赖通知”。
- API 永远返回 `delivery_scope=LOCAL_TEST_ONLY`、`external_delivery_confirmed=false`。即使状态是 `DELIVERED`，display text 仍明确“不代表飞书或邮件真实送达”。
- AI summary 没有外部调用，固定返回 `NOT_ENABLED` 和主管人工评价说明；AI 不可用不会影响结果或历史。

### 3.4 结果与时间线 API

- `GET /api/v1/me/result` 只允许 Learner，查询同时约束 actor role、organization、Outcome learner、Enrollment learner、Evaluation assignment、Handoff scope/owner 和 Delivery recipient。
- 响应包含最终 `PASS`、Outcome summary、主管总体反馈、四维结构化 feedback、Handoff owner/唯一 next step、Delivery 状态与 AI 未启用事实。
- `GET /api/v1/me/timeline` 只允许 Learner，逐域查询都带 organization + learner/owner + object chain；同组织另一 Learner 的 Review/Evaluation/Outcome/Handoff/Delivery/Event ID 全部不可见。
- 时间线只输出 title、时间、固定 object ID 和最小 details；不复制 Submission body、总体/维度反馈、显示名、token、附件或通知正文。
- 历史来自不可变 SubmissionVersion、受 WP-04 trigger 保护的 Review/Evaluation、不可变 Outcome/Handoff、原始 notification requested time 和 append-only Attempt。worker 更新 Delivery 当前态不会覆盖旧 attempt。
- cursor 是 base64url 编码的 `(occurred_at,item_id)`；非法、naive 或过长 cursor 返回 400；limit 为 1–100。GET 前后 bundle/count/status 完全不变。

### 3.5 Web

- `/app/result` 是 force-dynamic Server Component，以 `Promise.all` 并行读取 result/timeline，不在 Client Component 复制状态机，不把 session 或完整服务端对象下发给浏览器状态。
- 页面分为最终结论、结构化主管反馈、唯一交接、通知状态和不可变时间线；AI 未启用和外部送达未确认是可见文案，不使用含糊成功提示。
- 所有用户文本按 React 默认转义；没有 raw HTML、动态脚本、browser storage 或 client fetch。既有 CSP、httpOnly session 与 CSRF 合同继续生效。
- 390/768/1440 视口均无横向溢出；键盘 skip link、语义 heading/list/time/region 与 focus 样式沿用 UI Foundations。

## 4. 迁移与数据证明

### 4.1 空库 base↔head

最终 `make verify` 在 tmpfs 测试库执行 `0009 → base`，再执行 `base → 0001 → … → 0008 → 0009`、seed 与全部测试。Alembic downgrade/upgrade 均完成，最终 41 passed；Makefile 已使用 `sh -ec`，迁移失败会立即停止，不再继续 seed/pytest。

`0008_outcome_notifications` 建立 Outcome/Handoff/Outbox/Delivery/Attempt/Receipt 与不可变 trigger；`0009_notification_scope` 把 Outbox owner/actor 复合绑定到同组织 User，并把 Delivery 的 event/organization/recipient/outcome 复合绑定到 notification event。

### 4.2 WP-04 持久开发库升级

开工快照为 head=`0007_reviewer_workbench`：Invite=8、Assignment=5、TaskDefinition=1、TaskVersion=2、Submission=3、SubmissionVersion=5、Attachment=1、Review=5、Evaluation=3、Outcome=0。开工时还保存了这些表的稳定指纹；review/evaluation scope mismatch=0。

执行 `0007 → 0008` 用时 1.84 秒。升级后上述核心计数不变，Outcome/Handoff/Delivery 均为 0，review/evaluation scope mismatch 仍为 0。固定 TaskVersion 引用保持：

- definition `6fd4773d-8a4c-4886-910e-c61c1131fe45`；V1 `10000000-0000-4000-8000-000000000006`；rubric_version=1；
- 同一 definition；V2 `10000000-0000-4000-8000-00000000000c`；rubric_version=1。

早期真实浏览器随后明确新增一组本地验收数据，所以持久库成为 Invite=9、Assignment=6、Submission=4、SubmissionVersion=6、Review=6、Evaluation=4、Outcome/Handoff/Delivery=1。再执行 `0008 → 0009` 用时 2.09 秒；计数和固定引用保持，scope mismatch=0，新增链仍为 `HANDOFF_READY|READY|DELIVERED|SENT|1`。

一次复核 SQL 把真实表名 `invites` 写成 `invitations`，查询失败；迁移本身已成功。随后使用正确表名重跑并取得上述结果，失败查询没有计为数据证明。

## 5. 自动化、安全与最终门禁

| 门禁 | 结果 |
| --- | --- |
| `make bootstrap` | 通过，7.92 秒；API/Worker build、Web `npm ci`，0 vulnerabilities |
| 变更前 API 基线 | 38 passed；pytest 3.80 秒，命令 11.10 秒 |
| 变更前 Web 基线 | ESLint、TypeScript、Next production build 通过，11.21 秒 |
| WP-05 API/worker 定向 | 加入 Outcome/Handoff/timeline/真实 worker 后 41 passed，20.13 秒；scope hardening 后 41 passed，24.29 秒 |
| 第一条结果页 Web | lint、typecheck、Next production build 通过，6.64 秒 |
| 最终 `make verify` | 41 passed in 8.04s；Web lint/type/build；`isolation checks passed`；总计 28.95 秒 |
| Python 一致性/漏洞 | `pip check`: No broken requirements；临时容器 `python -m pip_audit -r requirements.lock`: No known vulnerabilities，69.57 秒 |
| npm audit | `npm audit --audit-level=moderate`: 0 vulnerabilities，1.30 秒 |
| 早期 Compose | `docker compose up -d --build --wait` 全部健康，37.87 秒 |
| 最终 Compose | API/Web/Worker/DB/DB-test 候选镜像与健康等待通过，39.28 秒 |
| HTTP smoke | 0.225 秒；health/Web=200，未认证 result/timeline=401，Reviewer result/timeline=403 |
| OpenAPI | 125,342 bytes；SHA-256 `6c712fd67130a9b8045d25e7aa30d87ab5e6126b31fd02905f27307420b4dde7`；result/timeline 与 schemas 的 jq 断言通过 |
| Playwright | 既有 chromium-1232；真实邀请→提交→Reviewer HTTP finalize→worker→结果；最终 console 0 error/0 warning |
| 三视口 | 1440/768/390 均 `scrollWidth == clientWidth`；桌面/移动截图视觉检查通过 |

显式执行 `security-best-practices` 并完整读取 Python/FastAPI、通用 JavaScript/browser、Next.js、React 参考后的复核结果：

- API role、organization、owner 与 object scope 同时存在；同组织另一 Learner 和 Reviewer 越权都有自动化负向证据；
- Outcome/Handoff/Delivery/Event 使用复合固定 scope，数据库拒绝将一个 event 跨接到另一 recipient/outcome；
- strict Pydantic、参数化 SQL、行锁、expected revision、幂等记录、唯一约束、lease token 和 immutable trigger 共同覆盖 IDOR、重放、并发与历史覆盖；
- 通知 payload 只有 `outcome_id/template_version`，Outbox/Audit/worker log 不含正文、反馈、显示名、token 或附件；最终 Compose worker 日志扫描未命中真实 smoke 称呼、正文或 Evaluation ID；
- OpenAPI 不存在通知状态管理写接口；production 配置拒绝 fixture identity、默认/复用 secret 与 LOCAL_TEST adapter；
- Web 无 raw HTML、危险 URL、浏览器凭证存储、动态脚本或不必要 client-side data fetch。

## 6. 浏览器证据

- [早期真实结果页](../output/playwright/wp05-early/.playwright-cli/page-2026-07-20T21-16-43-516Z.png)
- [最终 1440 视口](../output/playwright/wp05-early/.playwright-cli/page-2026-07-20T21-27-22-783Z.png)
- [最终 768 视口](../output/playwright/wp05-early/.playwright-cli/page-2026-07-20T21-27-27-447Z.png)
- [最终 390 视口](../output/playwright/wp05-early/.playwright-cli/page-2026-07-20T21-27-31-742Z.png)

Playwright 严格沿用 `~/Library/Caches/ms-playwright/chromium-1232`，没有执行 install/install-browser。skill wrapper 无执行位，全部成功调用均通过 `bash`；`open` 显式传入配置，配置内是既有 Chrome for Testing 的 `executablePath`。早期成功窗口约 2 分 43 秒，最终刷新与三视口约 28 秒；这是自动浏览器 smoke，不是真人 UAT。

## 7. 失败、重试与分段耗时

没有为分析或实现伪造总人时；只记录可核验命令和浏览器时间。以下失败均未计为通过：

| 分段 | 失败与处置 |
| --- | --- |
| ops doctor | helper 返回 `Not a compatible Muchen Journey repository`；按技能继续已有 Make/Compose，没有造第二套脚本 |
| 0008 首轮 | Handoff 复合 FK 没有完全相同的 Outcome unique key，迁移事务回滚；旧 Make 继续导致 22 failed/16 passed 的连锁输出。补 exact unique 后重试 |
| 原子 bundle 首轮 | ORM 同一 flush 中 Handoff 先于 Outcome，2 failed/36 passed，9.22 秒；改为事务内 staged flush 后 38 passed，15.22 秒 |
| WP-05 定向 | 新增 worker/timeline 后 41 passed，20.13 秒 |
| 持久库 | `0007→0008` 1.84 秒；第一次复核 SQL 表名拼错，改正后 counts/fixed refs/scope 全通过；`0008→0009` 2.09 秒 |
| browser early | 首次未显式传 `--config`，CLI 退回系统 Chrome 并失败；没有安装浏览器，显式 config/executablePath 后成功 |
| 0009 首轮 | revision ID 超过 Alembic `varchar(32)`，迁移回滚；旧 Make 继续产生 25 failed/16 passed。缩短 ID，并把 Make 改为 fail-fast；随后 41 passed，24.29 秒 |
| final verify 首轮 | 测试 helper 使用 0 秒 lease，两个 worker 会立即偷取尚在处理的事件；另一个 production 断言先被不安全默认 secret 拒绝。收紧 lease/poll>=1，正常并发用 30 秒 lease，崩溃测试显式模拟过期，并提供合法独立 production secrets；该轮 39 passed/2 failed，18.87 秒，不计通过 |
| final verify 重试 | 41 passed + Web + isolation，28.95 秒 |
| pip audit 首轮 | 临时容器将 executable 放在 `~/.local/bin`，shell PATH 找不到，26.77 秒；改用 `python -m pip_audit` 后通过，69.57 秒 |

## 8. 变更摘要

- Backend：新增 Outcome/Handoff 原子服务、完整 result/timeline routes/schemas、notification model/state 与固定 scope；保留 WP-04 REQUEST_REVISION/APPROVE 回归和 GET purity。
- Worker：实现可运行 CLI/long-running process、本地 adapter、claim lease、retry/dead、append-only attempt、receipt dedupe、crash recovery 和安全日志。
- Database：新增 0008/0009 migrations、不可变 trigger、状态/check/unique/复合 FK 和 legacy Outbox 升级；空库与 WP-04 持久库均验证。
- Web：重建 `/app/result` 为完整 Server Component，更新 server-only types、结果/反馈/交接/通知/时间线样式和 WP-05 footer。
- Contracts/docs：更新 OpenAPI、README、00、13，新增本 As-Built；16–20 未改写。
- Tests/runtime：新增 3 组 WP-05 集成测试，真实启动多个 worker 子进程；Compose 明确 local adapter 参数；Make migration fail-fast。

## 9. 已知债务、严格边界与 NOT_RUN

已知本地/后续债务：

- ops doctor 尚不识别此 Greenfield 仓库；未修复外部 helper。
- `GET /me/timeline` 当前先在内存组合一个 Learner 的 P0 事实再排序/分页；数据量与性能预算尚未通过 load/benchmark。未来优化必须保持同一 scope 和 cursor 合同。
- LocalNotificationReceipt 是本地测试 side-effect 证明，不是外部 provider receipt。Feishu/Email enum 只保留批准合同语义，worker 明确拒绝非 LOCAL_TEST adapter。
- DEAD 通知没有 WP-06 运营重驱 UI 或任意状态编辑接口；未来只能通过单独批准的运营命令追加重驱事实，不能直接改历史 attempt。
- 真实 AI 摘要未实现；页面直接展示主管人工反馈并明确 `NOT_ENABLED`。
- WP-03 本地附件存储/确定性扫描和 WP-04 fixture Reviewer 的既有本地限制继续成立。

以下门禁明确为 `NOT_RUN`：

- 真人 Learner/Reviewer 结果、修订、通知理解与交接签字 UAT；
- 真实 Feishu 或邮件发送、真实收件、provider receipt、退信/限流/凭证轮换；
- 真实 AI 服务、模型输出、降级告警和内容安全评审；
- staging/production 部署、真实身份提供方、TLS/cookie/secret/egress 配置和物理 PostgreSQL/object ACL；
- 备份恢复、PITR、迁移 rollback、灾难恢复、生产告警与 SLO 演练；
- release candidate 冻结、SBOM/镜像签署、双人发布批准、G4/G5 发布签署和生产观察；
- WP-06 运营 UI、版本化运营配置、离线导入、生产备份恢复/告警/发布运行。

仓库仍为无 HEAD、全部 untracked 的原始工作树形态；本工作包没有 stage、commit、push、建分支或部署。
