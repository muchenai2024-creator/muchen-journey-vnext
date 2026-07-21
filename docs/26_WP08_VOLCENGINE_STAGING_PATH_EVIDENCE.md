# 26｜WP-08 火山引擎 Staging 实施路径证据

日期：2026-07-22
状态：`IMPLEMENTATION_PATH_READY_CLOUD_NOT_APPLIED`
候选：`ff07ce47d20f3f6eb09d633b09292628fbb58e2a`
整体发布：`NO_GO`

## 已关闭

- 用户明确锁定火山引擎、华北2（北京）/`cn-beijing`、按量计费、¥500/月和上述完整候选；
- 独立资源命名、子域、VPC/SG/ECS/RDS/TOS、migration/runtime role、GitHub Environment secret、remote state、CI-only deploy 和回滚边界已形成仓库唯一受审路径；
- Terraform 使用官方推荐的 `volcengine/volcenginecc` 0.0.57，而非已停止维护的旧 provider；
- `wp08_staging.py` 将 provider/region/budget/candidate/origin 和同日报价设为 fail-closed 合同；
- staging Worker 使用显式 `DISABLED` adapter，只跳过 notification event，保留真实进程/heartbeat，且 production/LOCAL_TEST 继续拒绝；
- 候选三镜像部署引用固定为 WP-07 已核验 GHCR digest；Caddy 镜像固定 digest；
- deploy bundle 的 secret 文件为 `0600`，私有目录为 `0700`，旧域名/旧部署标识和 `LOCAL_TEST` 被拒绝。

## 当前未发生

- 火山引擎控制台尚未登录；未创建 IAM、VPC、安全组、ECS、RDS、TOS、DNS、证书或预算；
- 同日官方价格计算器总额仍未写入，`approved_monthly_estimate_cny=null`，因此 apply 门禁按设计失败；
- GitHub `staging` Environment 的火山引擎身份与 vNext secrets 尚未配置；
- 没有运行 migration、seed、TLS、browser smoke、旧凭证拒绝或物理 ACL 审计；
- candidate manifest 的 deployment 仍须保持 `NOT_RUN`。

因此该状态只代表 reviewed implementation path ready，不代表 physical staging、发布 GO 或 WP-08 关闭。下一动作是 Owner 登录火山引擎主账号，按 runbook 完成一次性 bootstrap 和同日报价；随后才允许 dispatch 唯一 staging workflow。
