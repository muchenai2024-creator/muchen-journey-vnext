# 22｜WP-06 受控运营、离线导入、恢复与发布门禁 As-Built

状态：`AS_BUILT`  
版本：V0.1  
日期：2026-07-21  
验证环境：本仓库 Docker Compose `local/test`、PostgreSQL 18.1、Python 3.14、Node.js 24、真实 Chromium headless shell 151  
候选标识：仓库没有 Git `HEAD`，因此使用 `wp06-local-no-head`；最终备份绑定源指纹 `34cbeac63957744d54abb1bf46c844171ba93a3508ab4df8a2c8ab45ef4832ab`  
发布状态：`NO_GO`。本文只证明本地构建，不是 staging/production、真人 UAT、发布批准或生产恢复证据。

## 1. 实施范围与上位合同

本轮只实施批准的 WP-06，并保持 docs/16–21 的历史事实不变。实现依据为 `REQ-BR-008`、`DEC-009`、Enrollment/Assignment/Review 状态机、组织与对象权限模型、审计最小化规则，以及 11 号文档的导入/恢复/发布边界。

完成项：

- 版本化 TaskDefinition/TaskVersion 与 config schema V1 的运营读取；发布后的 TaskVersion 继续由既有数据库不可变规则保护；
- 有明确业务意图的 Enrollment 列表、reviewer assignment 和 cancel 命令；
- HMAC 签名、SHA-256 校验、严格 schema、dry-run、幂等、并发重放安全、冲突隔离和脱敏报告的离线导入；
- 按 Operator、organization、object、时间和安全字段裁剪的审计查询；
- release/config/migration/API/DB/worker heartbeat/outbox/dead/permission-denial 的运行状态；
- 本地加密备份、签名 manifest、隔离恢复、0010→0009→0010 回滚/再升级和告警模拟；
- 严格发布门禁：缺项、`FAIL` 或 `NOT_RUN` 均为 `NO_GO`。

没有提供通用状态编辑器、任意 SQL、批量跨组织写入、旧系统连接、外部写回、生产 target 或将模拟证据登记为真人 PASS 的路径。

## 2. 受控运营合同

### 2.1 API 与页面

| 入口 | 意图 | 核心约束 |
| --- | --- | --- |
| `GET /api/v1/ops/task-definitions` | 读取版本化任务/config | Operator；组织 scope；已发布版本只读 |
| `POST /api/v1/ops/task-definitions` | 创建 TaskDefinition | 既有 WP-02 命令；reason/role/idempotency/content owner 约束 |
| `POST /api/v1/ops/task-definitions/{id}/publish` | 发布新 TaskVersion | 既有 WP-02 命令；新版本追加，不覆盖旧版本 |
| `GET /api/v1/ops/enrollments` | 运营列表与 `allowed_commands` | Operator + organization；最多 100；服务端决定动作 |
| `PUT /api/v1/ops/enrollments/{id}/reviewer` | 更换主管 | 同组织有效 Reviewer；reason≥10；expected revision；幂等键；行锁；已有开放 Review 时拒绝 |
| `POST /api/v1/ops/enrollments/{id}/cancel` | 取消 Enrollment | reason≥10；expected revision；幂等键；行锁；只允许 PENDING_IDENTITY/ACTIVE；已有 Review/IN_REVIEW 时拒绝 |
| `GET /api/v1/ops/audit` | 安全审计查询 | Operator + organization；默认 7 天、最多 31 天/100 条；过滤值 allowlist；详情安全字段 allowlist |
| `GET /api/v1/ops/runtime-status` | 运行状态 | Operator；release/config/migration/heartbeat/queue/dead；外部可观测明确为 false |
| `/ops` | 本地 Operator UI | 服务端组件；并行读取；无通用状态控件；明确本地候选与 NO_GO |

所有 Enrollment 写入同时产生 AuditEntry 与最小化 OutboxEvent。reviewer assignment 不替换 Review；cancel 只把允许取消的 Assignment 转为 `CANCELLED`，撤销仍处于 pending 的 join/invite，上位 Review/Evaluation 历史不被覆盖。

### 2.2 状态与并发

- Enrollment 仅允许 `PENDING_IDENTITY/ACTIVE → CANCELLED`；既有 `PENDING_IDENTITY → ACTIVE → COMPLETED` 路径不变。
- Assignment 仅在 Enrollment cancel 的受控语义下从 `AVAILABLE/IN_PROGRESS/SUBMITTED/NEEDS_REVISION → CANCELLED`；`IN_REVIEW` 拒绝取消。
- 写请求以 actor 行锁串行化幂等检查，再以对象行锁和 expected revision 防止 lost update。
- 同一个幂等键同载荷返回既有结果；同键异载荷、旧 revision、错误角色、跨组织对象均 fail closed。

## 3. 离线导入合同

### 3.1 明确边界

`DEC-009` 规定 P0 不导入旧业务数据。本实现因此只接受 `source_kind=SYNTHETIC_VNEXT_FIXTURE` 且 `target_environment=local|test` 的本地验证包；真实旧系统导出和导入仍为 `NOT_RUN`。CLI 没有网络客户端，不回写来源，也不暴露 HTTP 上传端点。

包结构固定为：

```text
package/
├── manifest.json
├── checksums.sha256
├── signature
└── data/
    └── enrollments.ndjson
```

验证顺序：拒绝 symlink/额外文件/尺寸异常 → 精确 SHA-256 checksum 行 → HMAC-SHA256(manifest bytes + newline + checksum bytes) → manifest schema/environment/org/operator/record count → 单行 NDJSON schema/尺寸/重复 source key → organization/operator/reviewer/task scope。

### 3.2 dry-run、应用、重放和冲突

- `dry-run` 执行完整密码学、schema 和 scope 检查，但数据库写入数为 0。
- `apply` 为每条合法记录创建 vNext 合成 User、RoleAssignment、ACTIVE Enrollment 与固定 TaskVersion Assignment。
- 相同 package checksum 重放返回 `package_replay=true`，不新增事实。
- 不同包包含同一 source key 且 record hash 相同，计为 source replay；hash 不同则隔离为冲突，不覆盖既有事实。
- 同组织并发 apply 先锁定受控 Operator，再重查 package ledger，避免双写。
- ImportBatch/ImportRecord 由数据库 trigger 拒绝 UPDATE/DELETE；报告只含聚合计数和原因计数，`contains_record_identifiers=false`、`source_writeback_executed=false`、`external_network_access_executed=false`。

本地 CLI drill 已证明：签名 fixture 创建、dry-run、apply、整包 replay、tamper 拒绝、跨包冲突、并发 replay 和非 local/test 拒绝。证据目录：`artifacts/wp06/import-cli-drill/`。

## 4. 数据库与迁移

`0010_wp06_governance` 新增：

- `worker_heartbeats`：worker name、release、status、last seen 与队列观测；
- `import_batches`：package checksum、source/target/operator、状态和聚合计数；
- `import_records`：batch/source key/hash、结果和隔离原因；
- package/source 唯一约束、查询索引、状态/计数约束和 import ledger 不可变 trigger。

验证分为两条，不通过修改事实来迎合旧 schema：

1. `make api-test` 每次精确删除并重建专用 `journey_next_test`，证明空库 `0001 → 0010` 后 seed 与全部回归；
2. `make migration-check` 在独立持久库建立 0009 合成事实，执行 `0009 → 0010 → 0009 → 0010`，逐次比较表计数与 TaskVersion 指纹。

最近持久迁移证据：`artifacts/wp06/wp06-20260720T223704Z-e61363b0/persistent-migration-report.json`，结果为 upgrade/downgrade/reupgrade 全部 PASS、`business_facts_preserved=true`、invalid constraints=0、critical invariant violations=0。

## 5. 审计、安全与隐私

- 所有 ops 入口依赖服务端 Actor 和 `Role.OPERATOR`，查询与对象 lookup 固定 organization scope；跨组织对象返回 404 以隐藏存在性。
- 审计 action/resource/result 过滤使用字符 allowlist，时间必须带 timezone 且单次不超过 31 天，limit 不超过 100。
- 审计详情只允许已批准的低敏标量键；reason、对象关系 ID 和未知字段不回显，仅在 `redacted_fields` 列字段名。
- 响应带 `Cache-Control: no-store` 与 `X-Content-Type-Options: nosniff`；TrustedHost、独立 session/CSRF、local/test fixture fail-close 合同保持回归。
- 导入与备份 secret 必须独立，签名 key 少于 32 字符或 config schema 非 V1 时启动失败；非 local/test importer 拒绝运行。
- 备份 key、密文、manifest、报告权限分别为 owner-only 0600，run directory 为 0700；key/symlink/未知 target 失败即停止。

按 `security-best-practices` 复核了 FastAPI、Next.js/React 与通用 Web 风险：未发现 `eval`、`dangerouslySetInnerHTML`、shell 执行、宽泛 CORS 或动态旧系统地址；HTTP 负向矩阵覆盖未认证、Learner/Reviewer 越权、缺幂等键、跨组织隐藏和超范围审计。Python `pip-audit` 最终为 `No known vulnerabilities found`，Web `npm audit --audit-level=low` 为 0 vulnerabilities。

## 6. React/Next.js 与真实浏览器证据

按 `vercel-react-best-practices` 复核：`/ops` 保持 React Server Component，无新增客户端 bundle；五个互不依赖的读取以 `Promise.all` 并行，写入使用 Server Actions；列表 key 稳定；没有 effect 驱动数据获取或重复客户端请求。

按 `playwright` 技能通过真实 Chromium 验证 `/ops`：

| 视口 | 结果 | 工件 |
| --- | --- | --- |
| Desktop 1440×900 | document width=viewport width；release/worker=`wp06-local-no-head`；console 0 | `output/playwright/wp06/.playwright-cli/page-2026-07-20T22-28-17-054Z.png` |
| Tablet 768×1024 | document width=768；无横向 overflow；console 0 | `output/playwright/wp06/.playwright-cli/page-2026-07-20T22-27-28-613Z.png` |
| Mobile 375×812 | document width=375、nav width=343；无横向 overflow；console 0 | `output/playwright/wp06/.playwright-cli/page-2026-07-20T22-27-52-437Z.png` |

页面逐张目视复核了标题层级、状态卡、NO_GO 提示、导航换行和小屏可读性。第一次 768px 检查发现 document width=855，调整表格/网格最小宽度与滚动容器后复测为 768。

## 7. 本地备份、恢复、回滚和告警

权威入口为 `docs/runbooks/WP06_LOCAL_OPERATIONS.md` 与 `scripts/wp06_ops.py`。脚本只允许 Compose `journey_next_dev` 和 `db-test`，无 staging/production 参数。

最终备份：`artifacts/wp06/wp06-20260720T224007Z-7aab83cc/`

- `backup-manifest.json`：HMAC 签名、source/openapi/明密文 checksum、release/config/migration、表计数、TaskVersion 指纹、不变量；
- `journey-next.dump.enc`：PostgreSQL custom dump，经 AES-256-CBC/PBKDF2 加密；
- `restore-rollback-report.json`：在新建 `journey_next_restore_7aab83cc` 隔离库完成 checksum/HMAC、restore、事实比较、0010→0009→0010，再删除精确临时库；
- restore/reupgrade PASS；invalid constraints=0；critical invariant violations=0；production/off-host backup/restore 均明确 `NOT_RUN`。

告警模拟证据：`artifacts/wp06/wp06-20260720T223735Z-0e185ced/alert-simulation-report.json`。健康输入无告警；故障输入同时得到 `WORKER_STALE`、`OUTBOX_BACKLOG_HIGH`、`NOTIFICATION_DEAD`、`RELEASE_REVISION_MISMATCH`、`MIGRATION_REVISION_MISMATCH`。没有发送真实 Feishu、邮件、Pager 或其他外部告警。

## 8. 自动化与运行结果

| 门禁 | 结果 | 关键事实/耗时 |
| --- | --- | --- |
| 基线 `make verify` | PASS | 实施前 41 tests；21.06s |
| 最新 API/领域/导入回归 | PASS | 51 tests；8.57s pytest，15.62s target |
| 空库 migration | PASS | 每轮测试库精确重建并 0001→0010 |
| 既有持久库 migration | PASS | 0009→0010→0009→0010；13.12s；事实不变 |
| Web lint/type/build | PASS | Next.js 16.2.10 production build |
| Compose | PASS | db/db-test/api/web/worker 全部 healthy；release/worker revision 一致 |
| HTTP permission negative | PASS | 7 类负向；未执行成功写入；报告 `wp06-20260720T223711Z-96413515` |
| Greenfield isolation | PASS | forbidden import/path/runtime scan |
| 三视口 Chromium | PASS | desktop/tablet/mobile、console=0、无 overflow |
| pip/npm audit | PASS | Python 0 known；npm 0 vulnerabilities |
| 本地 backup/restore/rollback | PASS | 最新 backup 2–3s；isolated drill约 7s；签名/指纹/事实一致 |
| 告警模拟 | PASS | healthy/failure 两组；0.07s；外部投递未运行 |
| 完整 `make verify` | PASS | 51 tests + migration + Web + isolation + HTTP + NO_GO contract；最终收口 34.33s（前一轮 33.31s） |

OpenAPI `contracts/openapi.json` 与运行时 schema 语义一致，API 版本为 `0.2.0-local`，包含全部 WP-06 ops 路由。

## 9. 发布门禁

`config/wp06_release_gate.local.json` 将已执行的九个本地检查登记为 `PASS`，以下八项保持 `NOT_RUN`：

- `real_human_uat`
- `real_external_notification`
- `staging_validation`
- `production_preflight`
- `physical_acl_validation`
- `off_host_backup_restore`
- `release_approvals`
- `real_observation_window`

`make release-gate-check` 返回 0，但只证明上述阻塞项仍存在且 decision=`NO_GO`。实际 `make release-gate` 输出同一 blockers，并由底层命令返回 3（Make 包装为非零），正确阻止 GO。不得把该“预期失败”改写为发布 PASS。

## 10. 失败与重试记录

1. ops doctor 首次使用了错误技能路径并返回 2；改用实际插件路径后运行成功，但报告 Greenfield 仓库“不兼容”。未伪造 P1 目标，转用仓库 Make/Compose 门禁。
2. 首轮 worker heartbeat 并发测试出现 insert race；改为 PostgreSQL atomic UPSERT 后通过。
3. 新测试曾因 fixture insert 顺序和 production config 缺 import key 失败；显式 flush 并补齐独立 key 后通过。
4. package replay 曾因重复关键字构造响应失败；统一 safe report 参数后通过。
5. 将含后期合法 `CANCELLED` 事实的数据库一路 downgrade 到 base 会在旧 schema 失败；没有重写历史，改为精确重建测试库证明空库链，并以 0009 合成持久事实证明 WP-06 的 0010↔0009。
6. 容器测试首次无法 import `scripts`；将项目根加入 pytest pythonpath 后通过。
7. 宿主 Python 3.9 不支持 `datetime.UTC`；运维脚本改为 `timezone.utc` 后通过。
8. 首版恢复不变量查询使用了错误的 Outcome 外键名；改为 `source_evaluation_id` 后恢复验证通过。
9. Python audit 首次工件路径错误、一次漏洞源查询长时间无输出并被中断；最终审计通过。收口重跑时宿主仍没有 `pip_audit`，改用只读挂载仓库的临时 Python 3.14 容器后得到 0 known vulnerabilities。
10. Playwright wrapper 直接执行因权限失败，改为 `bash` 调用；Chrome 安装需要 sudo 而被拒绝，安装技能支持的 Chromium headless shell 并在本地 config 指定真实 executable 后通过。
11. Playwright 首次在不存在的 workdir 启动失败；先创建规定的 `output/playwright/wp06` 后重试。
12. 平板首次发现 855px 横向 overflow；修复 responsive CSS，重建并在 768px/375px/1440px 全部复测通过。

失败均保留为本轮事实，没有降级断言、删除失败测试或把未执行项目标成 PASS。

## 11. 明确 NOT_RUN 与债务

### NOT_RUN

- 真人 Learner、Reviewer、Operator UAT、独立性/可用性结论与签字；
- 真实旧系统导出、签名包、数据核对、导入、切换和零写回观察；
- 真实 Feishu、邮件、GitHub 或告警外部写入；AI 摘要；
- staging/production 部署、预检、迁移、回滚、真实流量、SLO/观察窗和值守；
- 物理 DB、对象存储、身份、网络 ACL；真实对象存储和恶意文件扫描服务；
- 异机/KMS/生产备份创建、删除、恢复和灾难恢复；
- 发布审批、GO 签署和生产后观察。

### 债务

- `muchen-journey-ops` doctor/command map 面向旧 P1 仓库结构，本 Greenfield 仓库缺少其 P1 runbook/Make targets；这是工具兼容债务，未通过造假文件消除。
- 仓库没有 Git `HEAD`，无法绑定 commit SHA；本地候选暂以 `wp06-local-no-head` + HMAC 签名 source fingerprint 标识。不得据此发布。
- 备份加密 key 为同机本地 0600 文件，不是 KMS；备份恢复发生在同一 Compose 主机的隔离测试库，不证明异机或生产恢复。
- 可观测仅为本地结构化 stdout、数据库 heartbeat 与合成告警，不是外部 APM/告警链路。
- fixture identity、LOCAL_TEST notification、synthetic importer 与 Chromium 自动化只用于本地验证，不替代真实身份、通知、数据或真人 UAT。

## 12. 关键实现文件

- `apps/api/journey_api/ops_routes.py`
- `apps/api/journey_api/offline_import.py`
- `apps/api/journey_api/models.py`
- `apps/api/journey_api/schemas.py`
- `apps/api/journey_api/config.py`
- `apps/worker/journey_worker/main.py`
- `migrations/versions/0010_wp06_governance.py`
- `apps/web/src/app/ops/page.tsx`
- `apps/web/src/app/actions.ts`
- `apps/web/src/lib/server/api.ts`
- `scripts/wp06_ops.py`
- `docs/runbooks/WP06_LOCAL_OPERATIONS.md`
- `config/wp06_release_gate.local.json`
- `contracts/openapi.json`
- `tests/test_ops_governance_import.py`
- `tests/test_wp06_ops_script.py`
- `Makefile`、`compose.yaml`

本轮没有 stage、commit、push 或 deploy，没有生产/预发布写入，也没有修改 docs/16–21 的历史事实。
