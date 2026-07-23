# 26｜WP-08 火山引擎 Staging 实施路径证据

日期：2026-07-24
状态：`ALPHA_PILOT_SECRET_PATH_FIX_READY`
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

## 当前事实（2026-07-23）

- 独立 staging 项目中的部分 IAM、VPC、安全组、ECS、RDS/TOS 与 DNS 资源已由唯一受审 workflow 创建或纳管；资源和 remote state 的逐项事实以私有证据为准，公开仓库不记录账号、资源 ID、endpoint、IP、凭据或人员信息；
- 第二次 provision run `29945430858` 在无 destroy/replacement 的门禁通过后停止；RDS AllowList 与 DNS 查询权限的代码侧修复已由 PR #17 合并到主线 `1791ea6d89a290cf4ff41e5c4a9e27fb64d7213c`，required check 通过；
- 用户明确授权后已创建并附加全局只读策略 `journey-next-staging-dns-query-record-global`：正文仅允许 `dns:QueryRecord`，资源范围为 `*`，只附加给 `journey-next-staging-ci`，不受项目限制；授权页已反向核验。原 DNS/ECS/RDS/VPC/TOS 服务权限继续限定 `journey-next-staging`，本次未修改其他策略；
- 第三次 provision run `29974201816` 失败后没有自动重试；DNS state 精确纳管与 RDS 串行修复已由 PR #20 通过 required check 并合入主线 `af6443d9f4d3b25513c840557c9755e78758e092`，没有扩大 IAM；
- 本轮唯一新 provision run `29994013611` 已成功：DNS 精确 import、`0 add / 4 change / 0 destroy` saved plan、无破坏性门禁和 apply 均通过；应用部署步骤按 phase 正确跳过；
- 新实例 RDS CA 已取得并写入 GitHub `staging` Environment；Alpha deploy 已移除 DNS/provider/plan/apply 耦合。run `30026998583` 成功读取冻结 state、打开精确 runner `/32` 并准备 bundle，但在 migration 前因发布脚本错误读取全局 secret 路径停止；SSH 已确认关闭且未重试。release-local secret 路径修复与机器测试已就绪；migration、容器、TLS、browser smoke、真实身份和真人 UAT仍为 `NOT_RUN`，整体发布为 `NO_GO`。

## 2026-07-22 路径设计时未发生（历史快照）

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
- PR #8 合并后，run `29931062181` 已确认 KeyPair 全局读取不再出现；安全组创建仍因规则显式传入空 `prefix_list_id` 而把空 PrefixList TRN 纳入 `vpc:AuthorizeSecurityGroupIngress` 鉴权并停止。修复只删除未使用的空来源选择器，不扩大 `VPCFullAccess` 项目范围。
- PR #9 合并后，run `29931436619` 已越过 KeyPair 与安全组 IAM 鉴权；长耗时 refresh 最终仅在 TOS encryption `GetResource` 处返回 `InvalidTimestamp`。官方 provider 0.0.59 未包含该路径修复，因此 workflow 只为该精确错误增加一次只读 plan 重签重试；apply 与其他错误不重试。
- PR #10 合并后，run `29933251955` 的 plan 与 TOS refresh 正常完成，apply 在安全组出站规则描述的分号处以 `InvalidDescription.Malformed` 停止；修复仅把未支持的分号替换为允许的逗号。
- PR #11 合并后，run `29933635861` 确认描述已通过，但平台自动创建的默认全放行出站规则与 Terraform 重复声明冲突；根据火山引擎 VPC 官方行为，删除重复 IaC 出站项，不改变实际出站策略。
- PR #12 合并后，run `29934422323` 已创建并纳管 staging 安全组，随后在两个独立边界停止：RDS PostgreSQL AllowList 没有项目属性，因此项目限定的 `RDSPGFullAccess` 无法授权其创建；ECS 创建 API 同时缺少 Password 和 KeyPair。该 run 未创建 ECS、RDS，未执行 migration、seed 或应用部署，不得原样重试。
- 用户明确授权后，新建全局自定义策略 `journey-next-staging-rdspg-allowlist-cn-beijing`：仅含 RDS PostgreSQL AllowList 的 Create/Associate/DescribeDetail/Upgrade/Delete/Disassociate/Describe/Modify 八项动作，并以 `volc:RequestedRegion=cn-beijing` 限定地域。授权后反向核验其项目限制为“无”，原 `RDSPGFullAccess` 仍限定 `journey-next-staging`，未扩大其他 RDS 权限。
- ECS 不恢复账号级 KeyPair，也不扩大 `ECSFullAccess`。Terraform 改为一次生成 30 位 bootstrap password，仅保存在私有、版本化、SSE 加密的 TOS remote state且不输出；cloud-init 写入 deploy 公钥后关闭 SSH password、keyboard-interactive 和 challenge-response 登录，root 仅允许公钥登录。

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

## 2026-07-23 State 对账与破坏性计划修复

- 资源/state 对账已将既有 ECS 精确导入远端 state；对账 workflow 随后删除，长期入口仍只有 `.github/workflows/staging.yml`。远端 state 当前 serial 为 13，既有 ECS 保持 deletion protection，未被删除；
- IAM 已收敛为全局 CloudControl Create/Get/Update/Delete/GetTask 五项生命周期动作、华北2 RDS AllowList 八项、RDS SSL 两项和 EBS Describe 一项；DNS、ECS、RDS、VPC、TOS 服务权限继续限定 `journey-next-staging` 项目。`CloudControlFullAccess` 与 `TagFullAccess` 已删除，DNS 子区已转入该项目；
- 唯一 provision run `29942799357` 在 apply 前生成 `3 add / 4 change / 1 destroy`。CloudControl import 无法回读 ECS 的 EIP、镜像安全增强、Cloud Assistant、系统盘、bootstrap password 与 user-data 等创建期/write-only 属性，provider 因而错误提出替换；ECS deletion protection 阻止删除。RDS AllowList 同时因 `AssociateEcsIp` 绑定仍显式发送空 `ip_list` 被平台拒绝。TOS 发生一次就地更新，SSL、DNS 和应用部署均未开始；该 run 没有重试；
- 修复仅对官方 provider 标注为 write-only/创建期且实测不可回读的 ECS 属性使用精确 `ignore_changes`，同时增加 Terraform `prevent_destroy`；可回读的实例类型、区域、VPC/子网/安全组、项目、标签和 deletion protection 仍由 Terraform 管理。AllowList 的 `AssociateEcsIp` 绑定改为完全省略 `ip_list`；
- 所有 apply 路径（主基础设施与关闭 SSH）现在都必须先生成 saved plan，再把 `terraform show -json` 直接管道交给 `wp08_plan_guard.py`。任一 action 含 `delete`，包括两种 replacement 顺序，立即 fail closed；plan 值不写日志、不提交也不进入 artifact；
- 本节只代表代码修复与本地机器门禁通过，未授权或执行新的 provision。候选 deployment 继续为 `NOT_RUN`，整体发布继续为 `NO_GO`。

## 2026-07-23 第二次 Provision 与精确阻塞

- 用户明确授权后仅执行一次 `phase=provision`：run `29945430858`，workflow HEAD `bc76d1d813b193c18f96a4da364732f7af2b0967`，候选仍为 `670661865f708a835997596ed5b74904809564a5`；没有自动重试；
- saved plan 为 `2 add / 5 change / 0 destroy`，`WP08_TERRAFORM_PLAN_GUARD=PASS`。apply 完成 ECS 与 TOS 的原地收敛后，在两个并行资源处失败：RDS AllowList 把 computed `IpList` 作为空值发送并被 `InvalidAllowListIPList.InvalidIPList` 拒绝；DNS Record 因 CI 缺少 CloudControl 所需的全局只读 `dns:QueryRecord` 而被拒绝；
- DNS 子区、`DNSFullAccess`、ECS、RDS、VPC、TOS 仍限定 `journey-next-staging` 项目。待授权的 IAM 增量必须只有全局 `dns:QueryRecord` 一项，不得扩大为全局 `DNSFullAccess`；
- AllowList 修复把 `security_group_bind_infos` 明确设为创建期不可变嵌套集合，禁止配置 `ip_list`，并由机器检查锁定；安全组资源仍受 Terraform 管理。官方 provider 对 SetNestedAttribute 的已知限制决定了不能通过补齐空字段来更新该绑定；
- deploy 失败清理同步收窄：只要 remote state 初始化成功，`always()` 清理即运行，并只 target staging 安全组；清理 plan 仍须通过无 destroy/replacement 门禁，避免失败路径继续修改其他资源；
- 本轮未执行 migration、seed、应用容器、TLS 或 browser smoke。候选 deployment 继续为 `NOT_RUN`，整体发布继续为 `NO_GO`。

## 2026-07-23 DNS 最小权限与第三次 Provision

- 用户明确授权创建并附加全局只读策略 `journey-next-staging-dns-query-record-global`。控制台创建结果、策略语法和授权结果已核验：唯一 action 为 `dns:QueryRecord`，resource 为 `*`，只附加 `journey-next-staging-ci`，项目限制为“否”；项目限定的 DNS/ECS/RDS/VPC/TOS 权限均未改动；
- 权限完成后只触发一次 `phase=provision`：run [`29974201816`](https://github.com/muchenai2024-creator/muchen-journey-vnext/actions/runs/29974201816)，workflow HEAD `6dbcb80de9639d3f9adf650c31d549f3e3964e07`，候选仍为 `670661865f708a835997596ed5b74904809564a5`；没有第二次 dispatch 或自动 apply 重试；
- saved plan 为 `2 add / 4 change / 0 destroy`，`WP08_TERRAFORM_PLAN_GUARD=PASS`，因此不是破坏性计划门禁失败。RDS SSL 在 apply 中成功启用；两个 DBAccount 更新与 SSL 独占操作并发，被平台以 `instance is in exclusive status` 拒绝；
- DNS Record 创建返回 `AlreadyExists`，说明目标记录已经存在但当前 Terraform remote state 未完整收录。后续必须先以只读事实核验并精确 import/纳管该记录，禁止删除记录后重建；RDS SSL 与两个账号更新必须显式串行，避免同一实例上的独占操作并发；
- 本轮未执行 migration、seed、应用容器、TLS、browser smoke 或旧凭证拒绝。当前状态为 `PROVISION_PARTIAL_APPLY_RECONCILIATION_REQUIRED`，候选 deployment 仍为 `NOT_RUN`，整体发布继续为 `NO_GO`；任何新的 provision 都需要独立授权，不得原样重试。

## 2026-07-23 DNS State 纳管与 RDS 串行修复

- 用户以“按下一步推进”授权完成 DNS 精确纳管、RDS 独占操作串行化、受保护主线复验，并在全部门禁通过后只执行一次新的 provision；该授权不包含自动重试、production 部署或新增 IAM 权限；
- 唯一 staging workflow 新增只读 DNS 事实核验：复用项目限定的 `DNSFullAccess` 执行 `ListRecords`，按 host/type/line/TTL/status/remark/当前 ECS EIP 全字段匹配且要求唯一结果；RecordID 只在 run 内 mask 后用于同一 remote state 的精确 import/identity 核对，不落 Git、artifact、公开文档或新 secret；
- Terraform 将 RDS 变更锁定为 `SSL → migration account → runtime account`，避免平台独占状态下并发更新；DNS 导入之后仍必须生成 saved plan，并由现有 destroy/replacement 拒绝门禁检查后才允许 apply；
- 修复由 PR #20 合入受保护主线，required check 与主线 Candidate Gate 均通过；本地私有证据引用为 `GH_RUN_29994013611`。
- 合入后只触发一次 `phase=provision`：run [`29994013611`](https://github.com/muchenai2024-creator/muchen-journey-vnext/actions/runs/29994013611)，workflow HEAD `af6443d9f4d3b25513c840557c9755e78758e092`；DNS import 成功，saved plan 为 `0 add / 4 change / 0 destroy`，`WP08_TERRAFORM_PLAN_GUARD=PASS`，apply 为 `0 added / 4 changed / 0 destroyed`；
- `Prepare private deploy bundle`、镜像部署、外部 TLS 验证和 SSH 清理均按 provision phase 跳过，没有 migration、seed、容器或域名发布；当前状态为 `PROVISION_CONVERGED_RDS_CA_REQUIRED`。下一步需取得该 RDS 实例当前 CA 并写入 GitHub staging Environment；deploy 需要新的明确授权，候选 deployment 继续为 `NOT_RUN`，整体发布继续为 `NO_GO`。

## 2026-07-23 RDS CA 与首次 Deploy

- 火山引擎控制台反向核验目标 staging RDS 已启用 SSL、强制加密并允许 TLS 1.2/1.3；下载的新 CA bundle 只含一张可解析的 `CA:TRUE` PEM 证书，剩余有效期超过 30 天。证书正文未写入日志、Git 或公开证据；
- CA 已通过 stdin 以 base64 PEM 写入 GitHub `staging` Environment secret `WP08_RDS_CA_PEM_B64`，随后只按名称与更新时间确认 secret 存在，没有读回 secret 内容；
- 写入前重新执行候选、仓库、workflow、secret presence、最新 provision 与并发运行复验；候选 `670661865f708a835997596ed5b74904809564a5` 的受保护主线门禁和三镜像 registry digest 保持通过，最新 provision run `29994013611` 成功，且 dispatch 时没有其他 staging run；
- 用户明确授权后只触发一次 `phase=deploy`：run [`29997923817`](https://github.com/muchenai2024-creator/muchen-journey-vnext/actions/runs/29997923817)，workflow HEAD `936502fe75213250e0d91e6fe789e8cd127ea269`；没有自动重试；
- deploy 的候选合同、remote state 初始化和 DNS 精确对账均通过；saved plan 为 `0 add / 5 change / 0 destroy`，`WP08_TERRAFORM_PLAN_GUARD=PASS`。apply 在打开当前 runner 单一 `/32` 的临时 SSH 路径时停止：CloudControl 的安全组更新请求再次把空 PrefixList 引用纳入 `vpc:AuthorizeSecurityGroupIngress` 鉴权，越出项目限定资源边界；
- 该失败与预期的项目限定 VPC 权限模型不一致，不得通过授予全局 `VPCFullAccess` 或空 PrefixList 权限绕过。后续必须修正安全组嵌套集合/provider 更新模型或改用等价的最小、可清理临时访问路径，并重新通过代码、计划和权限复验后取得新的单次 deploy 授权；
- `Prepare private deploy bundle`、migration、镜像部署与外部 TLS 验证均被跳过；`always()` 关闭 SSH 步骤生成 `0 add / 1 change / 0 destroy` plan、再次通过破坏性门禁并成功 apply。当前未留下 runner SSH 放行，候选 deployment 继续为 `NOT_RUN`，整体发布继续为 `NO_GO`。

## 2026-07-23 最小部署通道修复

- 为避免继续扩大 IAM 或重构基础设施，Terraform 中 22 端口保持 `127.0.0.1/32` 关闭态，不再用 CloudControl 更新整个安全组嵌套集合；
- 同一 staging workflow 在关闭态 Terraform plan/apply 及破坏性门禁通过后，直接调用火山引擎 VPC API 添加当前 GitHub runner 的单一公网 `/32`；请求只包含 CIDR、TCP/22、accept、优先级和固定描述，不包含 `PrefixListId`、`SourceGroupId`，复用现有项目限定 VPC 权限；
- `always()` 清理按完全相同的规则属性撤销，并在添加和撤销后分别调用只读安全组查询确认精确规则数量为 1 和 0；不新增 provider、长期资源、Environment secret 或 IAM 策略；
- 本节只代表最小代码修复与本地复验，尚未触发新的 deploy。候选 deployment 继续为 `NOT_RUN`，整体发布继续为 `NO_GO`。

## 2026-07-23 最小修复后的 Deploy 尝试

- PR #23 通过 required check 并合入受保护主线后，只触发一次 `phase=deploy`：run [`30006425732`](https://github.com/muchenai2024-creator/muchen-journey-vnext/actions/runs/30006425732)，没有自动重试；
- 首次 plan 因精确 `InvalidTimestamp` 按既定合同只重签并重跑一次只读 plan；第二次得到 `0 add / 4 change / 0 destroy`，破坏性门禁通过；
- apply 中 RDS 账号与 TOS 原地收敛成功，ECS 因 Terraform 试图把实例当前 `KeepCharging` 改为 `StopCharging` 而被 CloudControl 以枚举校验失败拒绝。临时 SSH 规则尚未添加，因此 bundle、migration、容器、TLS 与清理均未运行；
- 月度预算本来按 ECS 整月运行估算；最小修复只把 `stopped_mode` 配置改为实例当前且该规格支持的 `KeepCharging`，不新增忽略项、权限、资源或费用假设。新的 deploy 仍需独立授权。

## 2026-07-23 硬停止与 Alpha 试点路径

- 安全组真实响应修复提交 `d20f263215f3abbd60e22d3c9d9529295085c063` 通过 PR #25 合入主线 `5e700afaeac6ef2bddcc83e6359e15e6f4bc1133`，required check 与 Mainline Candidate Gate 均通过；
- 按用户“一次且失败不重试”的边界，只触发 run [`30020569136`](https://github.com/muchenai2024-creator/muchen-journey-vnext/actions/runs/30020569136)。候选合同、remote state、DNS、无破坏性基础设施收敛、精确 runner `/32`、私有 bundle 均通过；
- `Deploy exact registry digests` 在 migration 和容器启动前以 `expected candidate marker is missing` 停止。原因是标记只由 ECS 创建期 cloud-init 写入，而既有导入实例按受审模型忽略 `user_data` 变化；TLS 验证被跳过，`always()` 已确认 SSH 入口关闭，没有第二次 dispatch；
- 根据硬停止条件，不再修补当前 provider/apply 链。仍复用同一 `.github/workflows/staging.yml`：`provision` 保留唯一 IaC 写路径；Alpha `deploy` 只读取冻结 state 输出，不运行 DNS import、provider refresh、plan 或 apply；
- 发布脚本直接核对授权候选和三个 GHCR digest，不再依赖 ECS 创建期标记；每次发布使用带 run ID 的新目录，失败不覆盖旧目录，GHCR 登录通过退出 trap 清理；
- 本节仅表示新路径代码与机器门禁就绪，尚未执行新的 Alpha deploy。真实身份与真人 Alpha UAT 仍不得提前标记为通过，整体发布继续为 `NO_GO`。

## 2026-07-24 Alpha Secret 路径失败与最小修复

- 用户精确授权候选 `670661865f708a835997596ed5b74904809564a5` 在 staging 只执行一次 Alpha `phase=deploy`，失败不重试；唯一 run [`30026998583`](https://github.com/muchenai2024-creator/muchen-journey-vnext/actions/runs/30026998583) 使用主线 `d393321aa24c3b5b7b04b49559af2f1686fcd729`；
- 候选合同、加密 state 初始化和冻结输出读取通过；DNS、Terraform plan/apply 与 CloudControl 步骤按设计跳过。精确 runner `/32`、私有 bundle 和 GHCR 登录通过；
- `deploy.sh` 在 migration 前以 `secret file api.env is missing` 停止。bundle 实际把六个 `0600` secret 放在本次 release 的 `secrets/`，Compose 也使用相对路径；脚本却固定读取 `/srv/journey-next-staging/secrets`，因此是单一发布包路径错误，不是 IAM、provider、RDS 或候选失败；
- 外部 TLS 被跳过，`always()` 已确认 runner SSH 规则为关闭态；未运行 migration、seed 或容器，未自动重试。失败 release 目录可能保留 root-only bundle，后续清理属于新的受控操作；
- 最小修复只把 `SECRETS` 指向当前 release 的 `$PWD/secrets`，并由 staging 校验测试锁定该合同；不新增 workflow、资源、IAM、secret 或依赖。新的 Alpha deploy 仍需独立精确授权。
