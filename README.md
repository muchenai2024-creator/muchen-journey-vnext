# Muchen Journey vNext

本仓库是 Muchen Journey vNext 的独立 Greenfield 代码库。批准文档、产品代码、测试和运行合同在此共同版本化；没有复制旧产品代码、数据库迁移或运行时兼容层。

本轮的不可逆前提是：下一版按 Greenfield 项目从零开发。旧系统可用于业务调研、历史数据盘点和验收对照，但不能成为新系统的代码依赖、运行时依赖、数据库依赖、部署依赖或写入回滚目标。

## 当前交付

- G0：DEC-001–016 与 00–15 号文档已批准用于构建；
- WP-00：独立 Web/API/Worker/PostgreSQL 基座、0001 migration、CI 和隔离扫描；
- G2 最小 walking skeleton：fixture 新人开始并提交 TSK-001，fixture 主管评审固定版本，系统生成 `HANDOFF_READY`；
- WP-01：真实一次性邀请、vNext 内部身份、`PENDING_IDENTITY → ACTIVE` Enrollment、独立可撤销会话、CSRF 与旧凭证拒绝；
- WP-02：稳定 TaskDefinition、发布后不可变 TaskVersion、固定版本 Assignment、服务端 Current Action Resolver，以及 Learner 当前行动/任务理解页；
- WP-03：不可变 SubmissionVersion 追加历史、服务端草稿恢复、首次/修订提交的幂等与并发合同，以及按 organization/owner/assignment/purpose 隔离的受控附件路径；
- WP-04：按 explicit reviewer + organization/object scope 裁剪的评审队列与详情、固定材料完整性、四维结构化 Rubric、并发安全的 start/finalize、不可变 Evaluation 历史，以及 Reviewer→Learner 修订/完成状态闭环；
- WP-05：评审通过后原子生成不可变 Outcome 与唯一 Handoff，事务 Outbox、本地 NotificationDelivery worker 的租约/重试/去重/死信合同，按 organization/owner/object 裁剪的跨域时间线，以及完整 Learner 结果页；
- WP-06：版本化 Task/config 只读运营视图，带角色/组织/对象 scope、原因、幂等键与 expected revision 的 reviewer assignment / enrollment cancel 命令，安全裁剪审计，revision/health/worker/observability 状态，签名离线 fixture 导入，以及本地加密备份、隔离恢复、回滚/告警模拟和 fail-closed 发布门禁；
- WP-07：本地候选基线、CODEOWNERS、分层 CI、固定摘要的基础/扫描镜像、依赖/secret/旧引用扫描、三进程 SPDX SBOM，以及绑定完整 Git SHA、OpenAPI hash、migration head、config schema 和 TaskVersion 清单的 release manifest；已增加仅在 `push main` 使用 `GITHUB_TOKEN` 向三个 canonical GHCR package 推送精确 SHA tag、远端解析 digest 并升级 manifest 的合同。该远端写入已授权由主任务复验后执行，本地仍为 `NOT_RUN`；
- 未实施生产/预发布部署、真实旧系统数据导入、真实 Feishu/邮件/告警、物理 ACL、异机/生产恢复、真人 UAT 或发布签署；这些项目仍为 `NOT_RUN`，当前发布判定必须是 `NO_GO`。

从 [文档地图](docs/00_DOCUMENT_MAP_AND_GOVERNANCE.md) 开始阅读。真人 UAT、物理 staging/production 资源、恢复/回滚演练与发布签署仍是 G4/G5 独立门禁，当前不是发布 GO。

## 本地运行

需要 Docker Compose 与 Node.js 24（仅直接运行 Web 工具时需要）。

```bash
docker compose up --build
```

- Web：<http://localhost:3000>
- API 健康：<http://localhost:8000/health/ready>
- 本地 OpenAPI：<http://localhost:8000/docs>

`/join#token=<invite_token>` 是新人 canonical 加入链接；fragment 不会发送到服务器，Web 在读取后立即从地址栏移除。邀请 token 只由 `POST /api/v1/ops/invites` 的创建响应返回，数据库仅保存 keyed hash。

当前仅在 `local/test` 允许 `X-Fixture-Role` 身份，用于 Operator 创建测试邀请以及保留 walking skeleton 回归。真实新人确认后使用 `journey_next_session` 独立会话；staging/production 配置会拒绝 fixture 身份和默认/复用的身份 secret。

WP-03 的本地附件实现使用 vNext 自有的隔离存储抽象和确定性恶意样本门禁，以便在 Compose 中验证 hash、大小、类型、文件名、对象 scope 与版本绑定。它不是生产对象存储或真实病毒扫描；真实 S3-compatible storage、病毒扫描服务和物理 ACL 仍是明确的 `NOT_RUN` 外部门禁。

Reviewer 工作台以服务端 `allowed_commands` 为唯一动作来源。`GET /reviews*` 只查询且按明确 Reviewer、组织和对象裁剪；finalize 要求固定四维 Rubric、每维反馈、总体反馈与 `APPROVE`/`REQUEST_REVISION`，结论写入后由数据库拒绝覆盖。

`APPROVE` 现在在同一数据库事务中写入最终 `Outcome(HANDOFF_READY)`、唯一 `Handoff(READY)`、最小化 Outbox 事件和 `NotificationDelivery`。`GET /api/v1/me/result` 返回服务端最终结论、结构化人工反馈、交接、通知状态与明确的本地范围；`GET /api/v1/me/timeline` 返回授权裁剪的 SubmissionVersion→Review/Evaluation→Outcome/Handoff→Notification 事实。两者都是无副作用读取。

Compose worker 只实现 `LOCAL_TEST` 通知适配器，具备 pending/processing/sent-or-failed、attempt、指数退避、lease、死信和 dedupe receipt；`local/test` 之外会 fail closed。页面上的 `DELIVERED` 只表示本地测试适配器已处理，始终同时显示 `external_delivery_confirmed=false`，不得解读为飞书或邮件已真实送达。真实 Feishu、邮件和 AI 服务均为 `NOT_RUN`。

`/ops` 是 WP-06 本地 Operator 入口。它不提供通用状态编辑器：TaskVersion 只读且发布后不可变；Enrollment 只能执行服务端返回的 `allowed_commands`，写入必须带原因、幂等键和 expected revision，存在评审事实时拒绝更换主管或取消。`GET /api/v1/ops/audit` 仅返回同组织、最多 31 天/100 条的安全字段，敏感详情只列出被裁剪字段名；`GET /api/v1/ops/runtime-status` 暴露 release、config schema、migration、API/DB/worker heartbeat、队列/死信和本地可观测模式，并明确 `external_observability_confirmed=false`。

离线导入是本地 CLI 合同，不是 HTTP 上传接口，也不连接旧系统。它只在 `local/test` 接受 HMAC 签名、SHA-256 校验、严格 manifest/NDJSON schema 的 `SYNTHETIC_VNEXT_FIXTURE` 包，先 dry-run，再以 package/source key 幂等应用；重放、跨包冲突和隔离原因写入不可变 ledger，报告不含记录标识符。示例命令：

```bash
mkdir -p artifacts/wp06/import-example
docker compose run --rm --no-deps -v "$PWD/artifacts/wp06/import-example:/import" api python -m journey_api.offline_import create-fixture /import/package
docker compose run --rm --no-deps -v "$PWD/artifacts/wp06/import-example:/import" api python -m journey_api.offline_import dry-run /import/package --report /import/dry-run-report.json
docker compose run --rm --no-deps -v "$PWD/artifacts/wp06/import-example:/import" api python -m journey_api.offline_import apply /import/package --report /import/apply-report.json
```

完整本地运维流程见 [WP-06 Runbook](docs/runbooks/WP06_LOCAL_OPERATIONS.md)：

```bash
make wp06-backup       # 仅 journey_next_dev；加密、签名 manifest
make wp06-drill        # 仅恢复到 db-test 的新隔离数据库并回滚/再升级
make wp06-alert-sim    # 只产生合成告警判定，不发送外部消息
make release-gate-check
make release-gate      # 当前预期非零并输出 NO_GO
```

## 验证

```bash
make verify
```

该命令精确重建测试数据库，执行空库迁移/种子/51 个 API 与领域测试、带既有事实的 0009↔0010 升降级、Web lint/类型/生产构建、Greenfield 隔离扫描、真实 Compose HTTP 权限负向矩阵，并验证发布门禁保持 `NO_GO`。历史事实保留在 16–21 号 As-Built 中，不会被 WP-06 改写；本轮实现、失败重试、浏览器/灾备证据和 `NOT_RUN` 边界见 [WP-06 As-Built](docs/22_WP06_CONTROLLED_OPERATIONS_IMPORT_RECOVERY_RELEASE_EVIDENCE.md)。依赖安全审计单独运行：

```bash
cd apps/web && npm audit --audit-level=low
```

Python 漏洞审计使用临时容器运行 `python -m pip_audit -r requirements.lock`，不把审计工具加入产品依赖或改写锁文件。

WP-07 分层门禁和候选工件入口为：

```bash
make ci-fast             # PR 快速层，目标小于 10 分钟
make ci-main             # 主线完整本地门禁
make candidate-package   # 仅对 clean、已有 40 字符 HEAD 的候选生成 digest/SBOM/manifest
make candidate-registry-check  # 只校验三个 canonical GHCR SHA tag；不登录、不 push
```

`candidate-package` 输出到被 Git 忽略的 `artifacts/wp07-candidate/`，本地默认不会 push。mainline workflow 只在 `push main` 且四项显式保护条件满足时，将同一批本地候选镜像推到 `ghcr.io/muchenai2024-creator/muchen-journey-vnext-{api,web,worker}:<full-sha>`；禁止 `latest`，不修改 GitHub 设置或部署环境。完整事实见 [WP-07 As-Built](docs/24_WP07_CANDIDATE_BASELINE_SUPPLY_CHAIN_EVIDENCE.md)。
