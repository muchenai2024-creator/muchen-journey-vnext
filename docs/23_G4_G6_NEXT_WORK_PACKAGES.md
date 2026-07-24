# 23｜G4–G6 下一批工作包定义

状态：`APPROVED_FOR_BUILD`
版本：V0.5
日期：2026-07-23
建议 Owner：Product Owner + Tech Lead + QA/UAT Owner + Release/Ops Owner  
依据：00–15 号开发前批准文档，以及 16–22 号 As-Built 已实现事实  
当前发布判断：`NO_GO`

变更说明：WP-07 已关闭；WP-08～WP-15 的编号、范围和顺序已批准，且用户已授权 WP-08～WP-13 按“独立任务、单一 WIP、主任务复验”自主推进。当前唯一活跃工作包为 WP-08；WP-09～WP-15 均未激活。外部权限、真人、时间窗口和生产写入仍须遵守各工作包的精确授权边界，计划批准不得替代这些授权。

## 1. 结论

WP-00～WP-06 已覆盖批准的 P0 产品实现，并取得本地 `LOCAL BUILD VERIFIED`。下一批不新增产品模块，而是把项目从 G3“P0 完整业务”推进至：

```text
G4 候选与 UAT → G5 独立试点 → G6 正式切换
```

下一批按单一 WIP 串行执行：

```text
WP-07 → WP-08 → WP-09 → WP-10 → WP-11
      → WP-12 → WP-13 → WP-14 → WP-15
```

其中 WP-07～WP-12 以工程和机器证据为主；WP-13、WP-14 必须由真实角色完成；WP-15 涉及生产写入和正式切换，必须获得精确候选、环境和窗口的当轮明确授权。

## 2. 进入下一批前必须锁定的执行输入

以下不是重开 DEC-001～016，而是把已批准方向替换为可执行的物理值：

1. [x] Git 远端目标已锁定并完成仓库创建、本地 `origin` 绑定、`main` push、远端 CI/GHCR 和保护规则闭环，见 2.1；
2. [ ] staging 平台、区域和域名已锁定；证书责任人与全部 production 物理值仍待关闭；
3. [ ] staging PostgreSQL 与 S3-compatible storage 已锁定；secret/KMS、日志/APM/告警物理值仍待关闭；
4. [ ] vNext 独立飞书应用、回调域名、应用 Owner 和测试租户；
5. [ ] 5 名 Learner、2 名独立 Reviewer、1 名 Operator、1 名 QA Recorder 的受控名册和排期；
6. [ ] Release/Ops 值守人、Security/Data 审批人、生产双人批准组合；
7. [ ] 14 天试点的开始条件、停止联系人、支持渠道和指标记录责任人。

这些值不应写入公开仓库中的敏感配置；仓库只记录资源标识、Owner、证据引用和非敏感 manifest。

### 2.1 已锁定的 Git 远端目标

| 项目 | 结论 |
| --- | --- |
| 平台 | GitHub |
| Owner | `muchenai2024-creator` |
| 仓库名 | `muchen-journey-vnext` |
| 可见性 | Public（用户在理解源码、历史、Actions 与工件公开风险后明确批准） |
| 默认分支 | `main` |
| 本地远端名 | `origin` |
| Canonical URL | `https://github.com/muchenai2024-creator/muchen-journey-vnext.git` |
| SSH URL（可选） | `git@github.com:muchenai2024-creator/muchen-journey-vnext.git` |

锁定理由：02/10/11 号文档要求独立仓库、保护分支、CI/CD 和不可变候选；当前已连接 GitHub profile 为 `muchenai2024-creator`，没有可用 organization 安装。初始 Private 因 GitHub Free 无法启用保护规则；用户在获知源码、历史、Actions、工件及外部副本不可收回风险后明确要求改为 Public，以关闭当前单人阶段的保护分支门禁。Public 是当前批准值，未来改回 Private 或迁入 organization 必须作为独立治理变更，不能临时切换候选来源。

当前事实：已于 2026-07-21 使用 GitHub 账号 `muchenai2024-creator` 创建仓库 `muchenai2024-creator/muchen-journey-vnext` 并绑定 Canonical URL。run 29803354837 暴露并固定两项 runner 可移植性缺口；run 29804468895 与最终证据 run 29804985537 全绿，三镜像完整 SHA 标签、远端 digest、registry-mode manifest 与下载工件均复验通过。仓库随后按用户明确决策改为 Public；`main` 已由 GitHub API 验证为强制 PR、严格 `WP-07 / quick`、线性历史、会话解决、管理员 enforcement，且禁止 force-push/删除。`mainline` 继续在合并后的 `push main` 完成全量门禁和 GHCR 发布。

## 3. 工作包总览

| 工作包 | 阶段 | 主要关闭项 | 退出结论 |
| --- | --- | --- | --- |
| WP-07 候选基线与供应链 | G4 前置 | 无 Git HEAD、无不可变候选、远端 CI/保护分支/SBOM 缺失 | `CANDIDATE_BASELINE_READY` |
| WP-08 物理独立 Staging | G4 | 独立运行时、DB、网络、secret、域名、CI 发布身份和旧系统不可达 | `STAGING_ISOLATION_VERIFIED` |
| WP-09 真实身份与权限 | G4 | Reviewer/Operator 飞书身份、真实 cookie/TLS、撤销/限流和物理权限矩阵 | `IDENTITY_AND_ACCESS_VERIFIED` |
| WP-10 真实附件与文件安全 | G4 | S3-compatible storage、短时 URL、扫描、隔离、生命周期和物理 ACL | `FILE_SECURITY_VERIFIED` |
| WP-11 真实通知与可观测 | G4 | 飞书投递、provider receipt、限流/重试/DEAD、外部 APM/告警 | `INTEGRATIONS_AND_OBSERVABILITY_VERIFIED` |
| WP-12 候选硬化与灾备 | G4 | 性能/SLO、安全、保留删除、异机备份恢复、RPO/RTO、N↔N+1 回滚 | `RC_TECHNICALLY_READY` |
| WP-13 内容校准与真人 UAT | G4 | Reviewer 校准、5 秒理解、AT-UAT-001..008、键盘/辅助技术 | `UAT_SIGNED` 或 `NO_GO` |
| WP-14 14 天独立试点 | G5 | DEC-010 KPI、真实流量、支持介入、缺陷趋势和观察窗口 | `PILOT_ACCEPTED` 或 `STOPPED` |
| WP-15 生产切换与观察 | G6 | 生产预检、双人批准、部署、切流、观察、旧系统只读边界 | `RELEASE_GO` 或 `NO_GO` |

## 4. WP-07｜候选基线与软件供应链

### 目标

把当前“无 Git HEAD、全部文件未跟踪”的本地构建转化为可审查、可重建、可绑定证据的唯一候选基线。

### 追溯

- `ISO-MUST-001/002/008`；
- `REQ-NFR-001/010`；
- `AT-ISO-001`、`AT-ARCH-005/007`；
- 10 号文档 Git/WIP/候选规则；11 号文档发布工件。

### 交付物

- 首个受审查 Git commit、受保护 `main`、CODEOWNERS/责任人和远端仓库；
- PR 快速门禁与主线门禁；从空 runner 执行依赖安装、迁移、测试和构建；
- Web/API/Worker 镜像 digest、SBOM、依赖/secret/旧引用扫描；
- release manifest：完整 commit SHA、OpenAPI hash、migration head、config schema、TaskVersion 清单；
- 候选工件不可在部署机现场重建；
- `muchen-journey-ops` Greenfield 兼容债务登记为工具任务，不通过复制旧 P1 runbook 解决。

### 退出门禁

- 精确 40 字符 SHA 可关联源码、镜像、合同和测试；
- main 可从空环境重复构建；旧仓库未挂载仍通过；
- 无 staged/unreviewed 漂移；只有一个活跃候选；
- CI 失败归属明确，快速层目标不超过 10 分钟。

### 权限边界

远端仓库创建、Public 可见性、本地 `origin`、WP-07 `main`/GHCR 写入和保护规则均已获授权并完成；协作者或其他 GitHub 设置仍属于后续外部写入，执行前需要用户明确授权。

### 本地 As-Built 状态

WP-07 实现与证据见 24 号文档：quick/mainline Make 与 GitHub Actions 合同、固定摘要、dependency/secret/legacy 扫描、三镜像 SBOM、release manifest、远端 CI/GHCR digest 和保护规则均已落地并复验。独立任务未做远端写入，主任务已按授权完成；WP-07 退出词为 `CANDIDATE_BASELINE_READY`，可按单一 WIP 启动 WP-08，整体发布仍为 `NO_GO`。

## 5. WP-08｜物理独立 Staging 基座

### 目标

在真实独立 staging 环境证明 vNext 不依赖本地 Compose 或旧系统资源。

### 追溯

- `ISO-MUST-003/004/007/008/009/012`；
- `DEC-003/013/014`；
- `AT-ISO-002/003/005`、`AT-ARCH-002/003/005`。

### 开工检查表（P0）

以下六项必须由 WP-08 独立任务重新取证并全部勾选；治理准备任务或旧工作包的结果不能替代本轮开工证据：

- [x] **逐工作包 Git/PR**：base `060dbe388e4c446191d64bb28387705c8960df21`；单一 `codex/wp-08-preflight-harness`；Owner/Reviewer=`@muchenai2024-creator` + 主任务复验；PR #3 由 `pull_request` 触发 required `WP-07 / quick` run `29844625968` 并 PASS。未混入其他工作包。
- [x] **浏览器预检**：仓库唯一 `browser-preflight/browser-smoke` 入口已存在并通过；固定 Chromium/config、证据目录、staging URL 前置条件、桌面/平板/手机、console、overflow、focus/键盘检查均可从声明状态重复执行。
- [x] **迁移与 fixture 预检**：migration 静态规则、唯一 head、空库和 WP-07 持久库升降级路径通过；staging 合成数据只由统一 fixture builder 生成，PII-free fixture manifest 列明表、字段和稳定引用。WP-08 不使用真实业务数据。
- [x] **停止态自举/工具检查**：本地服务停止后，quick/mainline 和候选门禁能自行启动所需依赖；必需工具及固定摘要显式检查，缺失或执行错误 fail closed；不依赖预启动 API、宿主 `rg`、未记录缓存或本机 Python 偶然状态。
- [x] **Ops V0.3+ 复验**：使用已安装的 `muchen-journey-ops` 运行 `doctor/status/gates`；profile=`greenfield-vnext`、doctor=`PASS`，并把当前 HEAD、候选、dirty paths、`NOT_RUN/NO_GO` 原样写入开工记录。禁止增加旧 P1 兼容文件或第二套运维入口。
- [x] **Public/私有证据边界**：在任何云资源、域名、secret、ACL 或 staging 写入前，明确私有证据存储、Owner、访问范围、保留期和公开引用格式；真实 tenant/app ID、域名/IP、人员、ACL、截图和 secret 不进入 Public Git，公开提交通过 secret/PII 扫描。

任一项未勾选时，WP-08 保持 `NOT_STARTED`，不得创建云资源、域名或 secret，不得执行 staging 部署。六项全部通过也只代表工程 Definition of Ready，不替代下述供应商、环境与外部写入授权。

2026-07-21 主任务复验：六项已全部关闭，证据见 25 号文档。

2026-07-22 用户进一步锁定火山引擎、华北2（北京）`cn-beijing`、按量计费、独立 IAM/VPC/SG/ECS/RDS/TOS/staging 域名。首次 ¥500/月尝试因成本超限停止；用户随后将预算提高为 ¥800/月并保留托管 RDS，完成 Next.js 16.2.11 / sharp 0.35.3 安全修复。主线候选 `670661865f708a835997596ed5b74904809564a5` 的 CI、候选打包和 GHCR digest 均通过，并获精确创建与部署授权；同日刷新后的月预测为 ¥656.26，距上限余 ¥143.74。

截至 2026-07-24，独立 staging 基础资源、RDS CA 和 remote state 已收敛。受控 mirror run `30063385826` 已把固定 Caddy 源 digest 复制到项目 GHCR 并验证目标 digest，Compose 已固定该目标。唯一 deploy run `30063847635` 成功拉取四个 GHCR 镜像，但第一次 Alembic 连接 RDS 时超时；migration、runtime grant、seed、应用容器和 TLS 均未执行，SSH 已关闭且没有重试。当前状态为 `ALPHA_PILOT_RDS_CONNECTIVITY_BLOCKED`；必须先只读对账 ECS→RDS 私网与 AllowList，真实身份、真人 UAT 与 WP-09 不得提前启动或转绿。

### 交付物

- 独立 staging Web/API/Worker、PostgreSQL、域名/TLS、secret store 和日志项目；
- migration role 与运行 role 分离；DB role 只能访问 vNext 数据库；
- CI 受限发布身份，个人机器不能直接部署 staging/prod；
- egress allowlist/deny：旧 API、旧 DB、旧 storage 和旧飞书多维表格不可达；
- release revision 在 Web/API/Worker/日志一致；
- staging 资源与旧系统命名空间、账号和故障域隔离证据。

### 退出门禁

- 从空 staging DB 部署并完成合成标准/修订路径；
- 旧系统停机或网络拒绝时 vNext 流程无影响；
- 旧凭证被拒绝；fixture identity 和 `LOCAL_TEST` notification 在 staging fail closed；
- 物理 DB/network/secret ACL 审计通过。

### 权限边界

创建云资源、域名、secret 和执行 staging 部署属于外部状态变更，需要明确环境和供应商授权。

## 6. WP-09｜真实身份、会话与授权验证

### 目标

实现并验证非本地 Reviewer/Operator 的 vNext 独立飞书身份绑定，以及真实浏览器、反向代理和撤销条件下的权限边界。

### 追溯

- `REQ-BR-002`、`DEC-006/014`；
- `AT-SEC-001/003/004/012`、`AT-ISO-003`；
- `AT-UAT-003/005` 的技术前置部分。

### 交付物

- 独立飞书应用、OAuth callback、一次性 state、防重放和 return URL allowlist；
- Reviewer/Operator 外部 identity 映射，业务域只引用内部 `user_id`；
- staging Secure/HttpOnly/SameSite cookie、TLS、CSRF、session rotation/revoke；
- 真实 client IP/代理配置、invite/session rate limit 和安全告警；
- Learner/Reviewer/Operator/Admin 的 organization + role + object scope 正负向矩阵；
- 身份/权限变更后的会话失效窗口实测。

### 退出门禁

- 真实 Reviewer/Operator 测试账号可进入且只能访问授权对象；
- 旧 cookie/token、跨组织、开放重定向、state replay、CSRF 和停用账号均被拒绝；
- 无共享账号、默认密码、旧 secret 或浏览器 token storage；
- 安全日志不含 token、手机号、飞书 subject 或提交正文。

### 权限边界

创建飞书应用、配置 callback、写 secret 或使用真实账号测试必须由对应 Owner 授权；不能由 fixture 证据代替。

## 7. WP-10｜真实附件存储与文件安全

### 目标

用真实 S3-compatible storage 和恶意文件扫描替换本地附件合同适配器，关闭文件安全和物理隔离门禁。

### 追溯

- `REQ-BR-004`、`REQ-NFR-005`；
- `AT-SEC-002/003/005/006`、`AT-CONTENT-004/008`；
- `AT-ARCH-003/004`。

### 交付物

- staging 独立 bucket/key namespace、最小权限角色和私有访问；
- presign/upload complete/download 的短时 URL 与二次授权；
- hash、size、MIME、文件名、owner/purpose 与 organization scope；
- quarantine + 恶意文件扫描 callback；扫描不可用时 fail closed；
- 附件生命周期、1 年保留、过期清理、孤儿对象回收和删除审计；
- storage/scan 故障注入、附件备份恢复和日志脱敏。

### 退出门禁

- 正常、超大、伪 MIME、恶意、跨 owner、跨组织、过期 URL 全矩阵通过；
- 未 `READY` 的附件不能进入 SubmissionVersion；
- Reviewer 只能下载固定授权版本；
- 物理 bucket ACL、网络策略和恢复样本通过。

## 8. WP-11｜真实通知与外部可观测

### 目标

接入真实飞书通知与独立 APM/日志/告警系统，证明异步副作用可恢复且不污染业务事实。

### 追溯

- `REQ-BR-009`、`REQ-NFR-007/009`；
- `AT-SEC-008/010`、`AT-API-006`、`AT-ARCH-004/005`；
- `AT-UAT-006` 的技术前置部分。

### 交付物

- vNext 独立飞书通知凭证、模板版本、recipient scope 与 provider receipt；
- 限流、超时、退避、凭证失效、重试、DEAD 和受控人工重驱；
- 通知模板最小化，不包含完整正文、附件或无关 PII；
- Web/API/Worker 独立日志/APM/release revision；
- 请求成功率/延迟、Current Action、submit/finalize、权限拒绝、outbox backlog/DEAD、DB/storage 健康仪表盘；
- 外部告警路由、Owner、值守和演练证据。

### 退出门禁

- 真实收件、provider receipt、错误收件人拒绝、退信/限流/凭证轮换通过；
- worker 停止和第三方故障时业务结果保持正确；
- 重试与并发不重复投递；DEAD 在 4 小时 SLA 内形成可处置告警；
- 日志敏感内容扫描通过。

### 权限边界

真实发送消息和外部告警会影响第三方收件人，必须在受控测试租户和明确名单内执行。

## 9. WP-12｜候选硬化、安全、性能与灾备

### 目标

冻结精确 RC，并用真实 staging/异机条件关闭技术发布门禁。

### 追溯

- `DEC-008/013/014`；
- `REQ-NFR-005/008/010`；
- `AT-DATA-008`、`AT-ISO-007`、`AT-ARCH-001/007`；
- 08、09、11 号文档发布前门禁。

### 交付物

- 仓库级 threat model 和 Sev-1/Sev-2 清零；
- dependency/image/SBOM/source map/secret/log 扫描；
- 数据保留任务：身份/提交/评价/结果/审计 3 年、附件 1 年、通知 180 天、幂等 30 天；删除/纠错请求 30 天流程；
- 常规读取和核心命令 p95 ≤1 秒的 staging benchmark；试点可用性 99.5% 仪表盘；
- 每日加密备份、KMS/受管密钥、异机副本；空白隔离环境恢复；
- RPO ≤24 小时、RTO ≤4 小时实测；
- vNext N→N+1→N 或维护模式演练，保留已接受事实；
- DB、Web、Worker、storage、identity、notification 故障卡演练；
- 精确 RC 的 release notes、已知问题、值守和回滚边界。

### 退出门禁

- 所有技术发布门禁绑定同一 SHA/image digest/migration/contract；
- 异机恢复后 schema、计数、约束和业务指纹一致；
- 性能、权限、幂等、故障注入和恢复预算通过；
- 无 Sev-1/Sev-2；Sev-3 有 Owner、期限和 Product/QA 接受；
- 候选冻结后无漂移。

## 10. WP-13｜内容校准与真人 UAT

### 目标

由真实 Learner、独立 Reviewer、Operator 和 QA Recorder 证明产品可理解、可操作、可评审；机器测试不能替代本工作包。

### 追溯

- `DEC-007/016`；
- `AT-UAT-001..008`、`AT-CONTENT-001..008`；
- `AT-UX-001/002/004/005/007`；
- `REQ-NFR-012`。

### 交付物

- 受控名册：5 名 Learner、2 名独立 Reviewer、1 名 Operator、1 名 QA Recorder；
- 三类样本的独立 Reviewer 校准：明显通过、明显需修订、边界案例；
- Learner 5 秒当前行动理解、首次任务理解、标准路径和修订路径；
- 邀请异常、提交超时/冲突、材料缺失、越权拒绝、通知失败、运营异常处理；
- 390/768/1280、纯键盘、200% 缩放和适用辅助技术人工验收；
- request id、困惑、帮助次数、缺陷和签署的最小化证据台账。

### 退出门禁

- `AT-UAT-001..008` 均由指定真人角色执行并签字；
- 5 秒理解率达到批准阈值；Reviewer Rubric 分歧已校准；
- 标准与修订路径都通过；
- 无 Sev-1/Sev-2；RC 未漂移；
- 若失败，输出 `NO_GO` 和单一 Owner 下一动作，不重复制造自动化假证据。

### 权限边界

Agent 只能准备脚本、环境和证据模板，不能代替真人点击、理解、独立判断或签字。

## 11. WP-14｜14 天独立试点与 KPI 观察

### 目标

在 vNext 独立环境用真实参与者验证 `DEC-010` 产品假设与运行护栏。

### 追溯

- `DEC-010/013/016`；
- `KPI-001..007`；
- G5 退出条件和 11 号文档 Phase B/C。

### 交付物

- 14 天试点起止时间、精确 release、参与者和支持/值守安排；
- 完成率、当前行动理解率、首次有效行动时间、评审周转、重复事实、支持介入、状态冲突；
- outbox/通知、权限拒绝、性能、DB/storage/worker 和缺陷趋势；
- D+1/D+3/D+7/D+14 检查点与真实 Owner 记录；
- 停止、继续或修复后重启试点的决定记录。

### 退出门禁

- 完成率 ≥80%；当前行动理解率 ≥90%；
- 90% 评审在两个工作日内；
- 重复事实和状态冲突为 0；
- 支持介入率 ≤20%；
- 可用性达到 99.5%，且缺陷趋势收敛；
- 任一护栏失败即 `STOPPED/NO_GO`，不能通过延长观察或改分母转绿。

### 权限边界

观察状态只能在真实时间点由责任人记录；Agent 不能预先制造 D+1/D+3/D+7/D+14 结果。

## 12. WP-15｜生产切换、正式入口与发布观察

### 目标

在全部 G4/G5 证据通过后，将批准目标批次切换到 vNext，并保持旧系统只读。

### 追溯

- `ISO-MUST-007/008/009/010/012`；
- `DEC-003/010/013/014`；
- 11 号文档 Preflight、部署、观察和 Go/No-Go。

### 交付物

- prod 独立 DB/bucket/identity/secret/APM/域名和物理 ACL；
- exact SHA/tag/image digest/migration/contract/config/UAT/试点签署一致性；
- 生产备份与有效异机恢复证据；
- 受限 CI 发布身份和双人批准；
- API/Worker/Web 兼容顺序部署、readiness/liveness 和封闭 smoke；
- 外部 DNS/网关/canonical entry 切换；旧路径在系统外说明/410；
- 观察窗口、值守、事故/回滚记录和独立 Production As-Built。

### 退出门禁

- 所有发布门禁绑定同一候选且无未解释 `FAIL/NOT_RUN`；
- 真实标准/修订路径、数据、安全、恢复和试点签字完整；
- 开放写入前获得双人批准；
- 观察窗口成熟且指标/护栏满足；
- 旧系统对目标对象只读，不作为 fallback 或恢复写入路径。

### 权限边界

生产预检、备份、迁移、部署、切流、回滚和开放写入必须在当前会话中获得精确 revision、环境和范围授权。定义本工作包不构成执行授权。

## 13. 明确不进入下一批

以下项目仍由现有 DEC 明确排除，不得借 G4/G5 扩大范围：

- AI Advisor、AI 摘要或 AI 自动结论（`DEC-012`）；
- 旧业务事实、旧附件或旧通知队列导入（`DEC-009`）；
- TSK-002、完整课程/考试/认证；
- 新手村、AI 学院、Talent OS、公会、积分、商城或多空间平台；
- legacy route、旧 API fallback、旧 session、旧数据库写回；
- 通用 CMS、任意状态编辑器、SQL 控制台或批量跨组织修复；
- 为未来模块预建 registry、微服务或空框架。

若要加入上述任一内容，必须先创建新的产品需求、DEC/ADR、旅程、数据/API/安全合同和验收，不得直接创建开发任务。

## 14. 单一 WIP 与执行方式

**执行锁定（2026-07-21）：WP-07～WP-12 统一采用“独立任务、单一 WIP、主任务复验”模式。**

- 同一时刻只允许一个工作包处于 `IN_PROGRESS`；
- 每个工作包使用独立开发任务，主任务负责范围、监控和独立复验；
- 前一工作包只有在本包退出门禁满足、As-Built 完成且主任务复验后，下一包才能启动；
- WP-07～WP-12 可在得到所需外部资源授权后按自主开发模式推进；
- WP-13～WP-15 遇到真人、时间、审批或生产边界时必须停下等待，不得自动跨越；
- 任何 `NOT_RUN`、`FAIL`、候选漂移或 Sev-1/Sev-2 都保持 `NO_GO`。

具体执行协议：

1. 主任务按顺序只派发当前工作包；独立任务不得提前实现、派发或修改下一工作包；
2. 独立任务开工前必须声明 `REQ-*`/`AT-*`、范围与非范围、适用 skill、预期文件和退出证据；
3. 独立任务交接必须包含精确分支/commit（如已形成）、实际差异、定向与完整门禁结果、As-Built/追溯更新、风险和未决项；
4. 主任务必须自行检查 Git 状态与差异、重跑与风险相称的门禁、核对 As-Built 和需求追溯，不以子任务“已完成”摘要代替验收；
5. 复验通过后由主任务将当前工作包标记为 `VERIFIED`，再创建下一独立任务；复验失败只返回当前工作包修正，不开启并行修复包；
6. 一个工作包获得的外部写入授权不得自动继承到下一工作包、其他环境或生产操作。

## 15. 批准与激活记录

本文件已升级为 `APPROVED_FOR_BUILD`，代表 WP-07～WP-15 的编号、范围、Owner 组合、顺序与单一 WIP 协议已锁定。执行仍遵循：

1. 当前只激活 WP-08；其退出词必须达到 `STAGING_ISOLATION_VERIFIED` 后才能激活 WP-09；
2. 第 2 节未关闭的物理执行输入必须在对应工作包开工前补齐；
3. 外部资源、角色或权限变更每次只按已说明的供应商、环境、动作与范围执行，不从计划批准推定；
4. WP-13、WP-14 的真人与时间证据不可由机器替代；
5. WP-15 的 production 写入、候选与窗口必须取得当轮精确授权；
6. 任一 `NOT_RUN`、失败、候选漂移或未关闭门禁均保持 `NO_GO`。
