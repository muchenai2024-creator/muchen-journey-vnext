# WP-08 火山引擎独立 Staging 运维手册

状态：`ALPHA_PILOT_RDS_CONNECTIVITY_BLOCKED`。本文仍是 Greenfield vNext 唯一 staging 资源与部署入口；不复用旧 P1 脚本，不授权 production。Provision 已收敛并冻结，新 RDS CA 已写入 `WP08_RDS_CA_PEM_B64`。应用 `deploy` 不执行 DNS 对账、Terraform plan/apply 或 CloudControl：只从加密 remote state 读取既有 ECS/RDS 定位值，再用 VPC API 临时添加并撤销当前 runner 的单一 `/32`。受控 mirror run `30063385826` 已把固定 Caddy 2.10.2 源 digest 复制到项目 GHCR，并验证目标 digest `sha256:b7c239fee65c44ac1dccfa76f88253f87e4d7a8ca27b92e419c86a967ecff171`。随后唯一 deploy run `30063847635` 成功拉取四个 GHCR 镜像，但第一次 Alembic 连接 RDS 时超时；SSH 已关闭且未重试。migration、runtime grant、seed、应用容器、TLS 与 browser smoke 仍为 `NOT_RUN`。

## 1. 已锁定授权

- Provider：火山引擎；Region：华北2（北京），ID=`cn-beijing`；
- 计费：全部按量计费（`PostPaid`）；月度硬上限：`¥800`；
- 实际部署候选：`670661865f708a835997596ed5b74904809564a5`；包含 Next.js 16.2.11 / sharp 0.35.3 修复；
- 入口：`https://staging-vnext.muchenai.com`；
- 资源：独立 IAM 项目/CI 子用户、VPC、子网、安全组、ECS、RDS PostgreSQL、TOS、委派 DNS 子区与 TLS；
- Owner：Liu Mowen。上述授权不包含 production、旧系统变更、真实飞书消息、真人 UAT 或将月预算扩大到 ¥800 以上。

`config/wp08_staging.json` 是机器合同。官方价格计算器同日总额未写入 `approved_monthly_estimate_cny` 时，`make wp08-staging-apply-check` 必须失败；合计高于 ¥800 时同样失败。

2026-07-22 的首次 ¥500 尝试已停止且未创建资源。用户随后将上限提高为 ¥800 并保留托管 RDS。新候选与同日报价均已关闭：PostgreSQL 17 高可用 1C2G 主备 20 GiB ¥396/月、ECS ¥177.26/月、TOS 20 GiB 保守 ¥3/月、EIP 出流量 100 GiB ¥80/月、RDS 备份 ¥0、DNS/ACME TLS ¥0，合计预测 ¥656.26/月，预算余量 ¥143.74。

## 2. 资源边界

- 新建项目与资源统一使用 `journey-next-staging-*`；禁止使用旧账号 AK/SK、旧 VPC/安全组、旧 ECS/RDS、旧 TOS bucket/prefix、旧部署脚本、旧 Sentry 项目或旧飞书应用。
- `staging-vnext.muchenai.com` 建为独立 DNS 子区；主域 `muchenai.com` 只增加该子区的 NS 委派，不把根区凭证交给 staging CI。
- ECS 只公开 80/443；Terraform 中 22 端口始终只接受 `127.0.0.1/32`。部署期间由同一 workflow 直接调用 VPC API 临时添加当前 GitHub runner 的单一 `/32`，`always()` 步骤按完全相同的 CIDR/协议/端口/优先级/描述撤销并反向确认；不得让 CloudControl 重写安全组嵌套集合。
- Alpha 应用发布冻结现有基础设施：`phase=deploy` 只做 backend init、`terraform output -raw`、临时 SSH、发布包、Compose 与 TLS smoke，不运行 provider refresh、DNS import、plan 或 apply。基础设施变化只能显式使用 `phase=provision` 并继续通过 saved-plan 破坏性门禁。
- ECS `stopped_mode` 固定为实例当前且该规格支持的 `KeepCharging`；预算按整月运行估算，不在 deploy 时尝试切换计费停止模式。
- 每条安全组规则只声明实际使用的来源选择器；CIDR 规则不得同时传入空 `prefix_list_id` 或 `source_group_id`，否则 CloudControl 会把空 PrefixList TRN 纳入 IAM 鉴权并越出项目边界。
- 安全组及规则描述只使用火山引擎允许的中英文、数字、空格、逗号、句号、下划线、等号和连字符；禁止分号等未支持标点。
- 自定义安全组创建时平台会自动加入允许 `0.0.0.0/0`、ALL 协议/端口的默认出站规则；Terraform 不得重复声明同一规则，否则 CloudControl 以 `InvalidSecurityRule.Conflict` 拒绝。出站收敛继续由主机 denylist 与隔离复验负责。
- RDS 只绑定 staging ECS 安全组，无公网地址；`AssociateEcsIp` 绑定不得配置 `ip_list`。`volcenginecc` 0.0.57 会在更新既有 `SetNestedAttribute` 时把 computed `IpList` 序列化为空值，因此该嵌套绑定仅在创建时配置，后续由精确 `ignore_changes = [security_group_bind_infos]` 保持不可变；安全组本身继续由 Terraform 管理。`journey_next_migrator` 拥有 schema，`journey_next_runtime` 禁止 DDL，只获 DML/sequence 权限；强制 TLS。
- RDS SSL 启用与 DBAccount 更新都会让实例进入独占操作状态，Terraform 必须显式串行这些资源，禁止并发提交；若平台返回 `instance is in exclusive status`，保留 partial state 并停止，不能自动重试。
- DNS API 返回 `AlreadyExists` 时，先只读核验记录内容与归属，再把唯一目标记录精确 import 到同一 remote state；禁止先删记录、扩大 DNS 权限或用第二条部署路径绕过。
- DNS 精确纳管固定使用项目限定的 `dns:ListRecords` 读取现有子区：同时匹配 `@`、A、默认线路、TTL 600、已启用、`vNext staging` 备注和当前 ECS EIP，必须且只能得到一个 RecordID。RecordID 先加入 Actions mask，只用于同一 workflow 的 `terraform import`；不得写入 Git、artifact、公开证据或新增 Environment secret。已有 state 地址则必须核对完整 import identity，不允许覆盖或重绑。
- TOS bucket 私有、版本化、默认 SSE-TOS AES-256；WP-08 只创建物理隔离资源，应用接入、presign 与扫描属于 WP-10。
- Worker 以 `APP_ENV=staging` + `NOTIFICATION_ADAPTER=DISABLED` 运行并上报 heartbeat；notification outbox 不会被领取。`LOCAL_TEST` 在 staging 仍启动失败，真实飞书 adapter 属于 WP-11。
- staging secret 的权威存储是 GitHub `staging` Environment；部署时经单次 SSH 加密通道落盘为 `0600`，不进入 Git、Actions artifact、Terraform CLI 参数或日志。Terraform 加密 TOS state 会保存 RDS account 的敏感属性，因此 state bucket 必须私有、版本化、仅 CI 子用户可读。
- ECS 创建所需的 bootstrap password 由 Terraform `random_password` 一次生成，仅保存在上述私有、版本化、SSE 加密的 remote state，并且不声明 output、不进入 GitHub secret、Actions 日志或 cloud-init。实例用它满足创建 API 的必填凭据合同；cloud-init 写入 staging-only deploy 公钥后立即将 SSH 收敛为 key-only。密码遗失不恢复、不用于日常登录，实例替换时生成新的随机值。

## 3. 一次性主账号 Bootstrap

Bootstrap 必须由主账号 Owner 在火山引擎控制台完成，不能使用旧系统子用户：

1. 创建资源项目 `journey-next-staging`；
2. 创建私有、版本化、SSE 加密的 TOS state bucket，名称使用 `journey-next-staging-tfstate-<random>`；
3. 创建无控制台登录能力的 IAM 子用户 `journey-next-staging-ci`；全局 CloudControl 自定义策略只允许 CreateResource/GetResource/UpdateResource/DeleteResource/GetTask 五项生命周期动作，不得使用 `CloudControlFullAccess`；RDS PostgreSQL AllowList 因资源创建前没有可用项目属性，额外使用全局自定义策略 `journey-next-staging-rdspg-allowlist-cn-beijing`，正文只允许 Create/Associate/DescribeDetail/Upgrade/Delete/Disassociate/Describe/Modify 八项 AllowList 动作，并以 `volc:RequestedRegion=cn-beijing` 限定地域；RDS SSL 两项与 EBS Describe 一项同样使用华北2最小自定义策略；DNS/ECS/RDS/VPC/TOS 服务权限只授权 `journey-next-staging` 项目及 state bucket 必需读写。CloudControl 创建 DNS Record 时会额外以 `project/*` 调用只读 `dns:QueryRecord`，因此只允许为 CI 身份增加这一项无项目限制的全局只读动作，不得增加其他全局 DNS 动作；不授予 `TagFullAccess`、旧项目或 IAM 管理权限；
4. 创建一次 AK/SK，并直接写入 GitHub repo 的 `staging` Environment secrets `VOLCENGINE_ACCESS_KEY` / `VOLCENGINE_SECRET_KEY`；不得复制到聊天、shell history、文档或本地 `.env`；
5. 创建 `staging-vnext.muchenai.com` 独立 DNS 子区，将控制台分配的 NS 记录委派到 `muchenai.com`，并把该子区转入 `journey-next-staging` 项目；把子区 ID 写入 Environment secret `WP08_DNS_ZONE_ID`；
6. 创建 staging-only Ed25519 deploy key；私钥/公钥分别写入 `WP08_DEPLOY_SSH_PRIVATE_KEY` / `WP08_DEPLOY_SSH_PUBLIC_KEY`。Terraform 通过 ECS cloud-init 把公钥写入实例，不创建账号级 ECS KeyPair，避免为 KeyPair 的创建后读取扩大 ECS 全局权限；
7. 建立费用预算 ¥800/月并设置 50%、80%、100% 告警。预算告警不是强制停机，Terraform 的报价门禁仍必须执行。

GitHub `staging` Environment 还需设置：

- Secrets：`WP08_TF_STATE_BUCKET`、`WP08_DNS_ZONE_ID`、`WP08_TOS_BUCKET_NAME`、两项 deploy key、两项 RDS password、`WP08_SESSION_SECRET`、`WP08_INVITE_SECRET`、`WP08_IMPORT_SIGNING_KEY`、`WP08_RDS_CA_PEM_B64`、`WP08_ACME_EMAIL`；
- Variables：`WP08_PRIMARY_ZONE_ID`、`WP08_SECONDARY_ZONE_ID`、`WP08_ECS_IMAGE_ID`、`WP08_ECS_INSTANCE_TYPE`。

密码/secret 均须由密码管理器独立生成。RDS password 为 20–32 字符且满足火山引擎复杂度；三个应用 secret 至少 32 字符且互不相同。

## 4. 报价与 Apply 前置

使用火山引擎价格计算器，在 `cn-beijing` 对同一组库存可用规格逐项记录 ECS 计算、系统盘、EIP 流量、RDS 两节点与 20 GiB、TOS、快照/备份和 DNS/TLS的月估算。将总额写入 `config/wp08_staging.json`；不得以促销首月价或未含流量/备份的数字通过门禁。

执行：

```bash
make wp08-staging-readiness
make wp08-staging-apply-check
```

唯一 Terraform 写路径执行 fail-closed 顺序：生成 saved plan → `terraform show -json` 直接管道到 `scripts/wp08_plan_guard.py` → 仅在没有任何 `delete` action 时 apply 同一个 saved plan。`delete/create` 与 `create/delete` 都视为 replacement 并拒绝；不得把 plan JSON 保存为 artifact、提交到 Git 或打印其中的敏感值。ECS 另有 `prevent_destroy`，不得为了通过计划而关闭。deploy 的 SSH 开关不再经过 Terraform/CloudControl；`scripts/wp08_security_group.py` 只允许一个公网 IPv4 `/32`，请求不得包含 `PrefixListId` 或 `SourceGroupId`，并在每次开关后只读确认精确规则数量。

然后在受保护 `main` 上通过同一 `.github/workflows/staging.yml` 完成两阶段首次部署：

1. `phase=provision`，candidate 输入完整 SHA，confirmation 输入 `DEPLOY_670661_TO_VOLCENGINE_STAGING`。该阶段只创建审查过的隔离基础设施，SSH 保持关闭，不准备 secret bundle、不迁移数据库、不启动应用；
2. provision 成功且 RDS SSL 已启用后，从新建实例下载当前 CA PEM，base64 后写入 `WP08_RDS_CA_PEM_B64`。不得复用旧实例或旧服务器上的 CA；
3. `phase=deploy`，使用相同 candidate 与 confirmation。该阶段只从冻结 state 读取既有 ECS/RDS 定位值，不执行 DNS、plan、apply 或 CloudControl；随后添加 runner 单一 `/32`，执行迁移、运行时授权、合成 seed、应用部署和 TLS 验证，并在 `always()` 步骤撤销该精确规则。

这条 workflow 仍是唯一写入口；两阶段不改变候选、预算或环境授权边界，本地个人机器不执行 `terraform apply` 或直连部署。

## 5. 部署顺序与证据

Workflow 顺序固定：provision 阶段执行合同检查 → TOS remote state init → Terraform validate → DNS 只读精确匹配与 state import/identity 核对 → Terraform saved plan → 破坏性门禁 → 关闭态 apply；Alpha deploy 阶段执行合同检查 → remote state 仅读取既有输出 → VPC API 临时 runner `/32` → 私有 bundle → GHCR digest pull → migration → runtime grant → PII-free seed → Web/API/Worker/edge → TLS/route → VPC API 撤销精确 SSH 规则。

三镜像必须使用 WP-07 已核验 digest，不能只用 tag。公开证据只记录 GitHub run ID、候选 SHA、门禁结果和非敏感资源类别；账号 ID、IP、DNS zone ID、RDS/TOS endpoint、SSH fingerprint、ACL 明细和截图只进入 `evidence/private/wp08` 或 90 天受控外部证据。

部署成功后运行 staging browser smoke，并由主任务复验：Web/API/Worker revision、migration head、fixture/LOCAL_TEST fail-closed、旧凭证拒绝、旧私网不可路由、RDS/TOS/secret ACL 和空库合成路径。全部通过前退出词仍不是 `STAGING_ISOLATION_VERIFIED`。

## 6. 回滚与停止

- 应用失败：`deploy.sh` 尝试重新启动 `PREVIOUS_RELEASE`；不回滚已接受业务事实，不自动 downgrade migration。
- Terraform plan/apply 失败：保留 state 和不含敏感值的精确错误引用；此时尚未添加临时 SSH 规则。VPC API、bundle、部署或验证失败时，`always()` 必须撤销并确认当前 runner `/32`；不得无审查重复。plan 出现任何 destroy/replacement 时必须在 apply 前停止，并由独立 PR 修复 drift 或重新取得破坏性操作授权；不得关闭 ECS deletion protection/`prevent_destroy` 绕过。
- CloudControl 长耗时 state refresh 若仅以精确 `InvalidTimestamp: The Signature of the request is expired` 失败，workflow 只允许重新签名并重跑一次只读 `terraform plan`；`apply` 不自动重试，其他错误继续 fail closed。
- 预算预测或实际成本超过 ¥800、候选/digest 不一致、CA/域名/ACL 不合格、旧资源引用出现：立即 `STOPPED / NO DEPLOY`。
- 首次部署无 previous release；失败时停止新容器，保留 RDS/TOS 供诊断。删除付费资源属于单独破坏性操作，需用户再次明确授权并先保留必要证据。
