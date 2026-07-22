# 26｜WP-08 火山引擎 Staging 实施路径证据

日期：2026-07-22
状态：`AUTHORIZED_CANDIDATE_BOUND_APPLY_PENDING`
候选：`670661865f708a835997596ed5b74904809564a5`
整体发布：`NO_GO`

## 已关闭

- 用户明确锁定火山引擎、华北2（北京）/`cn-beijing`、按量计费、¥800/月和上述完整候选；
- 独立资源命名、子域、VPC/SG/ECS/RDS/TOS、migration/runtime role、GitHub Environment secret、remote state、CI-only deploy 和回滚边界已形成仓库唯一受审路径；
- Terraform 使用官方推荐的 `volcengine/volcenginecc` 0.0.57，而非已停止维护的旧 provider；
- `wp08_staging.py` 将 provider/region/budget/candidate/origin 和同日报价设为 fail-closed 合同；
- staging Worker 使用显式 `DISABLED` adapter，只跳过 notification event，保留真实进程/heartbeat，且 production/LOCAL_TEST 继续拒绝；
- 候选三镜像部署引用固定为 WP-07 已核验 GHCR digest；Caddy 镜像固定 digest；
- deploy bundle 的 secret 文件为 `0600`，私有目录为 `0700`，旧域名/旧部署标识和 `LOCAL_TEST` 被拒绝。

## 当前未发生

- 火山引擎控制台已登录并只执行只读报价核验；未创建 IAM、VPC、安全组、ECS、RDS、TOS、DNS、证书或预算；
- 同日总报价已写入机器合同，但新的候选绑定变更仍须通过 PR 与受保护主线后才能 dispatch；
- GitHub `staging` Environment 的火山引擎身份与 vNext secrets 尚未配置；
- 没有运行 migration、seed、TLS、browser smoke、旧凭证拒绝或物理 ACL 审计；
- candidate manifest 的 deployment 仍须保持 `NOT_RUN`。

因此该状态不代表 physical staging、发布 GO 或 WP-08 关闭。首次报价触发的停止事实保持不变；后续预算重授权作为新的执行尝试单独记录。

## 2026-07-22 首次物理 Provision 与最小权限复盘

- GitHub staging run `29929929570` 使用完整候选和已批准确认词执行 `phase=provision`；候选合同、远端加密 state 初始化均通过，并创建了首批项目隔离资源；未运行 migration、seed、应用部署或外部 TLS 验证；
- 原先项目作用域的 `CloudControlFullAccess` 被 CloudControl API 拒绝。按用户明确授权，仅将该控制面策略改为全局；DNS/ECS/RDS PostgreSQL/Tag/VPC/TOS 六项服务策略逐项复核后仍限定 `journey-next-staging`；
- 重试 run `29929929570` 已越过 CloudControl 403，但在安全组创建冲突以及 ECS KeyPair 创建后的 `DescribeKeyPairs` 项目权限检查处停止；该 run 不得原样重试；
- 为保持 ECS 最小权限，不把 `ECSFullAccess` 扩大为全局。部署公钥改由 ECS cloud-init 写入 root `authorized_keys`，取消账号级 ECS KeyPair 资源；安全组、ECS、RDS、TOS 和 DNS 仍显式绑定 staging 项目或 staging 子区；
- 失败 run 产生的 Terraform partial state 和可能的孤立 KeyPair/安全组必须在下一次 apply 前完成精确核对；不得删除付费资源或扩大权限来绕过收敛。

## 2026-07-22 预算门禁

- 火山引擎官方价格计算器核验：华北2（北京）、按量计费、共享型 ECS `ecs.e-c1m2.large`（2C4G）、Linux、40 GiB PL0、EIP 按流量计费，按 720 小时估算为 ¥177.26/月；
- 火山引擎 PostgreSQL 创建页核验：当前最小高可用配置为 1C2G 主节点 + 1C2G 备节点，配置费用 ¥0.75/小时，即 ¥540/月；
- 两项小计已达 ¥717.26/月，尚未计入 TOS、备份和实际公网出流量，比授权上限 ¥500 高 ¥217.26；
- `approved_monthly_estimate_cny` 继续保持 `null`，`make wp08-staging-apply-check` 必须失败；
- 私有截图和失败记录引用：`PEV-WP08-20260722-BUDGET_GATE`。不含账号 ID、资源 ID、endpoint、凭据或 PII。

预算门禁触发后，本次执行状态为 `STOPPED / NO DEPLOY`。未创建 IAM、项目、VPC、安全组、ECS、RDS、TOS、DNS、证书或预算；未配置云凭据，未 dispatch staging workflow，WP-09 不得启动。后续只能由用户开启新的、范围明确的执行尝试：提高预算，或重新批准不使用托管 RDS 的架构变更。

## 2026-07-22 预算重授权与安全候选要求

- 用户将月预算上限提高到 ¥800，并明确保留火山引擎托管 PostgreSQL RDS；Region 与按量计费不变；
- 已核 ECS + RDS 固定基线仍为 ¥717.26/月，低于新上限，理论余量约 ¥82.74；TOS、备份和公网流量属于用量型费用，创建前必须刷新同日总报价并保持在 ¥800 内；
- 用户同时授权把 Next.js 固定到 16.2.11，并通过 npm override 将 sharp 固定到 0.35.3，完成兼容性和安全复验；
- 旧候选 `ff07ce47d20f3f6eb09d633b09292628fbb58e2a` 不再作为实际部署版本。必须等待包含安全修复的新完整候选 SHA、远端 required check 与 GHCR digest 验证后，再更新机器合同并启动物理 staging；
- 在此之前 `approved_monthly_estimate_cny` 保持 `null`，apply 门禁继续 fail closed，云端仍不写入。

本地兼容性与安全复验结果：

- `npm ls next eslint-config-next sharp --all`：Next.js 16.2.11、eslint-config-next 16.2.11、sharp 0.35.3 overridden；
- `npm audit --audit-level=low`：0 vulnerabilities；固定 Python 锁文件审计：No known vulnerabilities found；
- `make web-check`：lint、TypeScript、Next.js 16.2.11 production build 全部通过；
- `make ci-fast` 与 `make ci-main`：96 tests passed，OpenAPI、隔离、gitleaks、迁移、HTTP 权限负向和发布 NO_GO 合同全部通过；
- `make wp08-staging-readiness`：PASS，预算合同已为 ¥800；`make wp08-staging-apply-check` 按设计以“重授权后须刷新同日总报价”失败，不构成部署失败。

远端 required check 证据：PR #5 在包含依赖修复的提交 `43973cbcf9953b893cdee58ec1d5bcf9f70a5155` 上运行 [GitHub Actions 29888061258](https://github.com/muchenai2024-creator/muchen-journey-vnext/actions/runs/29888061258)，`WP-07 / quick` 于 1m57s 内通过。

## 2026-07-22 新候选授权与同日报价刷新

- PR #5 已合并到受保护主线，候选完整 SHA 为 `670661865f708a835997596ed5b74904809564a5`；[Mainline Candidate Gate 29888300206](https://github.com/muchenai2024-creator/muchen-journey-vnext/actions/runs/29888300206) 于 4m23s 内通过，三镜像 registry digest 均为 `VERIFIED`；
- 用户在当前对话明确授权该候选在火山引擎华北2（北京）、按量计费、月上限 ¥800 范围内创建独立 staging 资源并部署；
- RDS 控制台同日刷新：PostgreSQL 17、高可用 1C2G 主备、20 GiB、按量计费为 ¥0.55/小时，即按 720 小时估算 ¥396/月；ECS 既有同日报价为 ¥177.26/月，固定基线 ¥573.26/月；
- 预算模型保守计入单 AZ TOS 20 GiB ¥3/月、EIP 公网出流量 100 GiB ¥80/月；RDS 备份当前 0 折，DNS 子区与 ACME TLS 按 ¥0 计，月预测为 ¥656.26，距上限余 ¥143.74；
- 私有报价证据引用 `PEV-WP08-20260722-QUOTE_REFRESH`，不含凭据、账号 ID、资源 ID、endpoint 或 PII；
- 机器合同、Terraform、deploy bundle、工作流确认词及三镜像 digest 已重新绑定新候选；staging workflow 在门禁前从 run `29888300206` 下载精确候选 artifact，不依赖本地忽略目录。首次创建的新 RDS CA 只能在实例启用 SSL 后下载，因此唯一 workflow 使用 `provision` → 写入新实例 CA → `deploy` 的两阶段输入；两阶段共享同一 state、候选、预算和授权边界，不构成第二条部署路径。物理资源和 deployment 仍为 `NOT_RUN`，须待该绑定变更进入受保护主线后才允许执行。
