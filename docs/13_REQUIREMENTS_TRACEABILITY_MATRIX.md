# 13｜需求追溯矩阵

状态：`APPROVED_FOR_BUILD`  
版本：V0.6
日期：2026-07-21  
文档 Owner：Product Owner + QA Owner  
规则：P0 任一行缺少设计、数据/API 或验收引用，不得进入开发；实现 PR 必须引用对应 ID。

## 1. 业务需求追溯

| 需求 | 用户旅程/页面 | 领域/数据 Owner | API/事件 | 安全/权限 | 验收 | 当前状态 |
| --- | --- | --- | --- | --- | --- | --- |
| REQ-BR-001 邀请与加入 | JRN-001/003；`/join` | Invite、Enrollment | `POST /join/exchange`；invite.* | token hash/expiry/replay | AT-SEC-001；身份邀请矩阵；AT-UAT-003 | WP-01 已实现并自动化；真人 AT-UAT-003 `NOT_RUN`；见 17 |
| REQ-BR-002 身份与会话 | JRN-001/003；`/join` | User、ExternalIdentity、RoleAssignment | identity/session endpoints | session、CSRF、旧凭证拒绝 | AT-SEC-004/012；AT-ISO-003 | WP-01 已实现并自动化；物理身份配置审计 `NOT_RUN`；见 17 |
| REQ-BR-003 当前行动 | JRN-001/002；`/app`、task understanding | Enrollment、TaskDefinition、TaskVersion、Assignment；Resolver | `GET /me/current-action`、`GET /me/assignments/{id}`、task definition publish | Learner owner + org；Operator content owner；server allowed commands | AT-UX-001/002；resolver/权限/版本矩阵；AT-CONTENT-005 | WP-02 已实现并自动化；真人理解率/UAT `NOT_RUN`；见 18 |
| REQ-BR-004 任务与提交 | JRN-001/004；task page | Assignment、Submission、SubmissionVersion、SubmissionDraft、Attachment | start/draft/submissions/attachments/history；submission.created | org + owner + assignment + purpose；hash/type/size/name/scan；复合 FK | AT-DATA-003/005；AT-SEC-002/003/005/007；AT-UX-008；AT-UAT-001/004 | WP-03 本地实现并自动化；真人 UAT、真实对象存储/病毒扫描 `NOT_RUN`；见 19 |
| REQ-BR-005 主管评审 | JRN-001/005；review pages | Review、Evaluation | reviews/start/finalize；review.* | explicit reviewer + organization/object scope；GET 无副作用；DB 不可变 | AT-UX-004/005；权限/并发矩阵；AT-UAT-005 | WP-04 本地实现并自动化；真人 Reviewer 独立性/校准与 AT-UAT-005 `NOT_RUN`；见 20 |
| REQ-BR-006 修订闭环 | JRN-002；result/task | Assignment、Submission、SubmissionVersion、Review、Evaluation | 同一 submissions 命令按 allowed command 追加版本；history；revision_requested | 本人 + org + object；expected revision；旧版本/附件关联 DB 只读 | AT-DATA-002/003/005；AT-API-002；AT-UX-008；AT-UAT-002 | WP-03 本地实现并自动化；真实 Learner/Reviewer UAT `NOT_RUN`；见 19 |
| REQ-BR-007 通过与交接 | JRN-001；`/app/result` | Evaluation、Outcome、Handoff | `GET /me/result`；assignment.completed/outcome.created/handoff.ready | Learner owner + org/object；固定 Evaluation/Enrollment；DB 不可变 | AT-DATA-006；AT-UAT-001/006 | WP-05 本地实现并自动化；真人 AT-UAT-001/006 `NOT_RUN`；见 21 |
| REQ-BR-008 运营处理 | JRN-003/005；`/ops` | Invite、Enrollment、TaskDefinition/TaskVersion、Audit、ImportBatch/ImportRecord、WorkerHeartbeat | task definition publish；`GET /api/v1/ops/enrollments|audit|runtime-status`；`PUT /api/v1/ops/enrollments/{id}/reviewer`；`POST /api/v1/ops/enrollments/{id}/cancel`；离线 import CLI | Operator role + organization/object scope + reason + expected revision + idempotency；审计 allowlist/裁剪；无通用状态编辑器 | 运营命令/权限/并发/重放矩阵；AT-UAT-008；AT-SEC-011；AT-ISO-006；AT-DATA-007 | WP-06 本地实现并自动化；真人 Operator UAT、真实旧系统导入和发布运行 `NOT_RUN`；见 22 |
| REQ-BR-009 通知 | JRN-006；`/app/result` | OutboxEvent、NotificationDelivery、NotificationAttempt、LocalNotificationReceipt | notification.requested；本地 worker | organization + recipient + outcome 复合 scope；最小 payload/log；lease/retry/dedupe；非 local/test fail closed | AT-SEC-008；故障/崩溃/并发注入；AT-UAT-006 | WP-05 本地适配器实现并自动化；真实 Feishu/邮件收件 `NOT_RUN`，通知不阻塞核心结果；见 21 |
| REQ-BR-010 不可变历史 | 全旅程；`/app/result` timeline/history | SubmissionVersion、Review/Evaluation、Outcome/Handoff、OutboxEvent/NotificationAttempt | submission history；`GET /me/timeline`；所有写事件 | role + organization + owner + object 裁剪；事件/日志最小化；历史事实 DB 不可覆盖 | AT-DATA-005；审计结构测试 | WP-05 完成跨域时间线与 Outcome/Handoff/NotificationAttempt 不可变证明；早期 Task/Submission/Review 历史证据仍见 18/19/20；见 21 |

## 2. Greenfield 隔离追溯

| 要求 | 架构/交付控制 | 自动/人工验收 | 发布证据 |
| --- | --- | --- | --- |
| ISO-MUST-001 独立源码 | 新 Git repo；无 submodule/workspace 引用 | AT-ISO-001；dependency/import scan | WP-07 候选 commit、CODEOWNERS、clean-tree preflight 与 legacy/isolation scan；无 `rg` 时以严格 `grep` fallback 且扫描错误 fail closed；Public `main` 保护已由 API 验证；见 24 |
| ISO-MUST-002 独立依赖 | 公开依赖 + vNext 自有模块 | lockfile/SBOM/forbidden import | WP-07 固定 runtime/base/扫描器摘要，npm/pip audit、secret scan、三镜像 SPDX SBOM 与 canonical GHCR SHA-tag/digest 合同；见 24 |
| ISO-MUST-003 独立 DB | 新 DB/role；0001..0010 migration | AT-ISO-005；DB ACL/空库重建 | 空库 0001→0010 与既有事实 0009↔0010 本地 PASS；物理 ACL `NOT_RUN`；见 22 |
| ISO-MUST-004 无旧运行时 | egress allowlist；无旧 SDK/URL | AT-ISO-002；network deny | egress policy/report |
| ISO-MUST-005 独立身份 | vNext user/session/secret | AT-ISO-003；AT-SEC-004/012 | WP-01 逻辑隔离与配置 fail-closed 已自动化；staging/prod 物理 identity config audit `NOT_RUN` |
| ISO-MUST-006 无兼容路由 | 04 号唯一 route manifest | AT-ISO-004；AT-UX-009 | route scan |
| ISO-MUST-007 独立环境 | 资源清单与命名空间 | environment audit | signed env manifest |
| ISO-MUST-008 独立部署 | vNext CI/image/runtime | AT-ISO-001/007 | WP-07 run 29804468895 在实现 SHA `eb4035e…` 完成 mainline、三个精确 SHA GHCR 镜像、远端 digest 二次验证与 manifest/SBOM/TaskVersion 上传；`registry_push=VERIFIED`，protected main/deployment 仍 `NOT_RUN`；见 24 |
| ISO-MUST-009 独立可观测 | vNext log/APM/revision | AT-ARCH-005；告警演练 | WP-06 暴露 release/health/worker/backlog/dead 并完成本地告警模拟；外部 APM/告警 `NOT_RUN`；见 22 |
| ISO-MUST-010 vNext 内回滚 | N ↔ N+1 compatible rollout | AT-ISO-007 | WP-06 隔离恢复后 0010→0009→0010 与事实指纹本地 PASS；生产回滚 `NOT_RUN`；见 22 |
| ISO-MUST-011 离线导入 | signed export + importer | AT-ISO-006；AT-DATA-007 | WP-06 HMAC/checksum/dry-run/幂等/冲突隔离/不可变 ledger 本地 PASS；真实旧系统包 `NOT_RUN`；见 22 |
| ISO-MUST-012 旧系统只读 | no fallback/writeback | AT-ISO-002/007；UAT | importer 仅接受合成 vNext fixture，报告 `source_writeback_executed=false`；真实 cutover signoff `NOT_RUN`；见 22 |

## 3. 非功能需求

| ID | 要求 | 设计来源 | 验收 |
| --- | --- | --- | --- |
| REQ-NFR-001 | Greenfield 物理独立 | 02、06、10、11 | AT-ISO-001..007；AT-ARCH-002/003/006 |
| REQ-NFR-002 | 服务端状态与 allowed commands 权威 | 04、05、07 | resolver/状态矩阵；AT-UX-003；AT-API-002 |
| REQ-NFR-003 | 幂等、并发与安全重试 | 05、07 | AT-DATA-003；AT-API-002；AT-UAT-004 |
| REQ-NFR-004 | 不可变历史与审计 | 05、07、08 | AT-DATA-005；AT-SEC-011；审计测试 |
| REQ-NFR-005 | 身份、权限、隐私与文件安全 | 08 | AT-SEC-001..013；权限矩阵 |
| REQ-NFR-006 | 可访问性与响应式 | 04、09 | AT-UX-006/007；AT-UAT-007 |
| REQ-NFR-007 | 外部依赖可降级 | 06、07、11 | AT-ARCH-004；AT-API-006；故障演练 |
| REQ-NFR-008 | 性能与可用性预算 | 06、11；DEC-013 | benchmark、load、SLO dashboard |
| REQ-NFR-009 | 可观测与可诊断 | 06、11 | trace/revision/request id；告警演练 |
| REQ-NFR-010 | 部署、备份、恢复和回滚 | 11 | AT-DATA-008；AT-ISO-007；发布演练 |
| REQ-NFR-011 | 离线、可审计、幂等导入 | 05、11 | AT-ISO-006；AT-DATA-007 |
| REQ-NFR-012 | 真实角色 UAT | 09 | AT-UAT-001..008；签字证据 |

## 4. 页面到合同追溯

| 页面 | 主要需求 | 服务端读取/命令 | 核心状态 | 体验验收 |
| --- | --- | --- | --- | --- |
| `/join` | BR-001/002 | join exchange、identity confirm | Invite + Enrollment | UX-001/003；SEC-001/004 |
| `/app` | BR-003/007 | current-action、result | Enrollment/Assignment/Outcome | UX-001/002/003 |
| `/app/tasks/{id}` | BR-004/006 | assignment、start、submit、attachments | Assignment/Submission | UX-002/003/006/007 |
| `/app/result` | BR-006/007/009/010 | `GET /me/result`、`GET /me/timeline` | Evaluation/Outcome/Handoff/NotificationDelivery + immutable facts | UX-003；UAT-002/006；SEC-008 |
| `/review` | BR-005 | review list | Review | UX-004；SEC-002/003 |
| `/review/{id}` | BR-005 | detail/start/finalize | Review/Evaluation | UX-004/005/007 |
| `/ops`（Invites 仍由 API 命令创建） | BR-001/008 | ops invite commands；版本化 Task/config 读取；enrollment list/reviewer/cancel；audit/runtime-status | Invite、Enrollment、TaskDefinition/Version、Audit、WorkerHeartbeat | UAT-008；SEC-003/011；config/revision/negative HTTP tests；见 22 |

## 5. 状态迁移到测试追溯

| 聚合 | 迁移 | 必测风险 | 测试类型 |
| --- | --- | --- | --- |
| Invite | DRAFT→ACTIVE→CONSUMED | 过期、撤销、并发消费、重放 | Domain + DB + API + Security |
| Enrollment | PENDING_IDENTITY→ACTIVE；PENDING_IDENTITY/ACTIVE→CANCELLED | 半成品、重复 active、身份错误、原因/幂等/revision、存在 Review 时拒绝改写历史 | Domain + DB + API + Permission |
| TaskDefinition/Version | DRAFT→PUBLISHED；V1→V2 | content owner、reviewer scope、发布不变性、在途 Assignment 固定 V1 | DB + API + Permission + Migration |
| Assignment | AVAILABLE→IN_PROGRESS | 越权、重复 start、revision 冲突 | Domain + API |
| Assignment | IN_PROGRESS→SUBMITTED | 重复事实、附件、超时 | DB + API + Browser |
| Assignment | SUBMITTED→IN_REVIEW | GET 副作用、错误 reviewer | Domain + Permission |
| Assignment | IN_REVIEW→NEEDS_REVISION | Evaluation 原子、旧版本不变 | DB + API + Browser |
| Assignment | NEEDS_REVISION→SUBMITTED | version 递增、历史追溯 | DB + API + Browser |
| Assignment | IN_REVIEW→COMPLETED | 并发 final、Outcome 一次、通知降级 | DB + API + Worker + UAT |
| Notification | PENDING→SENDING→DELIVERED；PENDING/SENDING→RETRY_WAIT→SENDING；→DEAD | 租约、退避、并发、崩溃重放、重复投递、错组织/收件人/Outcome、核心结果独立 | Worker process + DB + API + Security |
| OfflineImport | VERIFIED→APPLIED/REPLAYED；冲突→QUARANTINED | 签名/checksum/schema、包与 source key 重放、并发应用、跨包冲突、零写回、报告脱敏 | CLI + DB + Concurrency + Security |

## 6. 决策到受影响文档

| DEC | 影响 |
| --- | --- |
| DEC-001/002 | 02、06、09、10、11、13；全部 ISO 验收 |
| DEC-003 | 02 资源清单、06 拓扑、10 WP-00、11 环境/发布 |
| DEC-004 | 03 范围、04 IA、05 模型、10 工作包 |
| DEC-005 | 06 技术栈、10 工程规则、11 工件 |
| DEC-006 | 03 BR-002、04 JRN、07 身份 API、08 session、09 测试 |
| DEC-007 | 03 用户/试点、09 UAT、11 试点切换 |
| DEC-008 | 05 保留、08 隐私、11 导入/归档 |
| DEC-009 | 05/11 导入、09 数据测试 |
| DEC-010 | 03 KPI、09 退出、11 观察/Go-No-Go |
| DEC-011 | 03 BR-007、04 结果页、05 Outcome、07 result API |
| DEC-012 | 03 非目标/范围、06 worker、07 AI、08 隐私、09 降级 |
| DEC-013 | 06 NFR、09 benchmark、11 备份/观察 |
| DEC-014 | 02 资源、08 密钥、11 发布/事故 |
| DEC-015 | 04 体验、14 UI token/组件、09 可访问性验收 |
| DEC-016 | 03 P0 范围、05 TaskVersion、07 配置 API、09 UAT、15 内容/Rubric |

## 7. PR 与发布使用规则

每个 PR 描述必须包含：

```text
Requirement IDs:
Decision IDs:
Acceptance IDs:
State/API/Data changes:
Isolation impact:
Test evidence:
Known risks/non-scope:
```

CI 后续应验证：

- 引用的 ID 在本目录存在且未 `SUPERSEDED`；
- P0 需求至少有一个自动化和一个适用的 UAT/人工验收；
- API/migration/route 变化更新对应矩阵；
- 新 route/command 无需求映射时失败；
- `BLOCKED_BY_DECISION` 需求不得进入产品实现。

## 8. G0 完成项与后续证据边界

以下构建输入已锁定；需要真人、物理环境或发布窗口的证明继续保留到 G4/G5，不以文档批准替代执行证据：

- [x] DEC-003..016 的最终构建选项、初始 Owner 和批准日期；
- [x] BR-002、BR-007 的明确产品合同；
- [x] KPI 阈值与试点样本规模；
- [x] 数据保留与 P0 不导入旧业务数据的边界；
- [x] API 路由、错误、事件与幂等机器实现初稿；OpenAPI 固化随本次基座验证生成；
- [x] 逻辑模型、0001 migration 与 walking-skeleton 权限 scope；
- [x] 低保真状态已实现为可运行页面，不另造一次性原型；
- [ ] G4：受控登记真实 UAT 名册、排期与签字证据；
- [ ] G4/G5：建立物理独立资源并由发布/事故 Owner 验证；
- [x] UI token、组件约束与实际 P0 任务/Rubric/SLA。

## 9. G4 候选基线追溯

| 工作包 | 需求/验收 | 本地机器证据 | 外部边界 | 当前结论 |
| --- | --- | --- | --- | --- |
| WP-07 候选基线与软件供应链 | ISO-MUST-001/002/008；REQ-NFR-001/010；AT-ISO-001；AT-ARCH-005/007 | `make ci-fast`、`make ci-main`、`make candidate-package`、`make candidate-registry-check`；完整 SHA/OpenAPI/migration/config/TaskVersion、三镜像 local digest/SPDX SBOM，以及 CI-only canonical GHCR push + remote digest verify 合同；见 24 | run 29804985537 PASS；GHCR 三镜像与 registry-mode artifact 已交叉复验。Public `main` 强制 PR + `WP-07 / quick`，管理员受约束，禁止 force-push/删除；部署仍 `NOT_RUN` | `CANDIDATE_BASELINE_READY`；可进入 WP-08，整体发布仍 `NO_GO` |
| WP-08 物理独立 Staging | ISO-MUST-003/004/007/008/009/012；DEC-003/013/014；AT-ISO-002/003/005；AT-ARCH-002/003/005 | `make wp08-staging-readiness`、`make wp08-staging-apply-check`、`make wp08-workflow-check`、Terraform validate 与 saved-plan destroy/replacement guard；DoR 与路径证据见 25/26 | provision 已冻结；run 30026998583 按设计跳过 DNS/import/plan/apply，在 migration 前因 release-local secret 路径错误停止并撤销 SSH。单行路径修复与测试已就绪；migration、应用、TLS、身份与 UAT 仍 `NOT_RUN` | `ALPHA_PILOT_SECRET_PATH_FIX_READY`；WP-09 未激活，整体发布仍 `NO_GO` |
