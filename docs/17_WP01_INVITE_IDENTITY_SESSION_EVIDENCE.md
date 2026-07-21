# 17｜WP-01 邀请、身份与会话构建证据

状态：`AS_BUILT`  
版本：V0.1  
日期：2026-07-20  
验证环境：本地 Docker Compose，未发布  
Owner：Liu Mowen（初始 Product + Tech Owner）

## 1. 本次完成范围

- 实现 Operator scope 下的邀请创建、查询与带理由撤销；创建命令幂等，并发同 key 返回同一邀请；
- 邀请使用高熵 token，数据库只保存 keyed hash；token 通过 `/join#token=...` 进入 Web，fragment 不发送到服务器且读取后立即从地址栏移除；
- 实现一次性 `POST /api/v1/join/exchange`，有效邀请原子创建最小 User 与 `PENDING_IDENTITY` Enrollment；无效、过期、撤销、已消费和并发失败不产生 ACTIVE Enrollment；
- 实现 `POST /api/v1/identity/confirm`，原子创建/确认 vNext 内部 User、`INVITE` ExternalIdentity、Learner RoleAssignment、ACTIVE Enrollment、首个 Assignment 与独立会话；已有 ACTIVE vNext User 可复用，DISABLED User 被拒绝；
- 实现 `GET /api/v1/session` 与 `POST /api/v1/session/logout`；会话为短期、可撤销、数据库只存 keyed hash，角色/用户停用后认证 fail-closed；
- cookie 会话写操作强制 double-submit CSRF；`return_to` 只允许 canonical `/app`；旧 Bearer、旧 cookie 与无效 vNext cookie 不会进入 fixture fallback；
- staging/production 禁止 fixture 身份，并要求 session/invite secret 长度合格、非默认且彼此独立；
- 邀请创建/交换/消费/撤销、身份确认和退出记录最小化 AuditEntry；领域事实写入同事务 outbox；
- Web 新增 canonical `/join`，确认后沿用 walking skeleton 的服务端 Current Action 与 Assignment，不引入前端身份状态机。

## 2. 需求与实现追溯

| 要求/验收 | 实现事实 | 自动化证据 |
| --- | --- | --- |
| `REQ-BR-001`、`AT-SEC-001` | Invite ACTIVE→CONSUMED/REVOKED/EXPIRED；hash、expiry、replay、并发锁 | `tests/test_identity_invites.py` 的创建幂等、并发创建、有效/无效/过期/撤销/消费/并发交换用例 |
| `REQ-BR-002`、`AT-SEC-004` | 内部 UUID、ExternalIdentity、独立 Session、CSRF、logout/revoke | 真实邀请会话、缺 CSRF、退出后 401、state replay/open redirect 用例 |
| `AT-SEC-012`、`AT-ISO-003` | 唯一 vNext cookie/secret；Bearer/legacy cookie 不被接受；fixture 非本地 fail-closed | 旧凭证拒绝、无效 vNext cookie 不降级、非本地 secret/config 用例 |
| Invite/Enrollment 状态不变量 | `0002_invites_identity_sessions`、行锁、唯一约束、部分唯一 active Enrollment | 空库 upgrade、重复 downgrade/upgrade、并发交换单赢家、撤销 pending Enrollment→CANCELLED |
| API/UX 合同 | 既有 identity/session/ops invite endpoints；`/join` 单一确认动作 | OpenAPI 生成、Next lint/typecheck/production build |

## 3. 机器验证结果

| 证据 | 2026-07-20 结果 |
| --- | --- |
| `make api-test` | `19 passed`；从空测试库执行 downgrade/upgrade/seed，覆盖 walking skeleton 与 WP-01 邀请/身份/session 正负向、幂等、并发、安全矩阵 |
| `make web-check` | ESLint、TypeScript 与 Next.js production build 通过；`/join` 为 dynamic canonical route |
| `make isolation-check` | `isolation checks passed`；未加入旧源码、旧 API、旧凭证或兼容路由 |
| `npm audit --audit-level=moderate` | `found 0 vulnerabilities` |
| `docker compose up --build --wait` | DB、API、Worker、Web 构建并健康启动；API 自动升级到 `0002_invites_identity_sessions` |
| 容器 HTTP smoke | `/health/ready`、`/join`、`/app` 返回 200；`/join` 页面包含邀请加入恢复说明 |
| 真实浏览器 smoke（合成数据） | fragment 读取后地址栏 hash 长度为 0；交换后展示权威用途；确认后进入 `/app`；local session 为 HttpOnly + SameSite=Lax、CSRF cookie 为 SameSite=Lax；退出后两个 cookie 均清除 |
| 机器合同 | `contracts/openapi.json` 由当前 API 生成，包含 ops invite、join exchange、identity confirm 与 session endpoints |

## 4. 安全与数据边界

- `invite_token`、join token、session token、CSRF 原值不进入数据库、AuditEntry、Outbox payload 或 URL query；
- Invitation create 的幂等 token 由独立 invite secret 确定性派生，重试可恢复但持久层仍只有 hash；
- JoinContext 最长 15 分钟，Session 默认 8 小时；非本地 cookie 为 Secure、HttpOnly（CSRF cookie 除外）、SameSite=Lax；
- 无效邀请统一返回受控恢复语义；rate limit 使用 HMAC 后的网络 client bucket，不保存原始地址；
- 最小审计仅服务 WP-01 安全事实，不提供通用审计查询、SQL/status editor 或运营后台。

## 5. 明确未做

- 未实现附件、对象存储、通知渠道、NotificationDelivery 或 worker 投递扩展；
- 未实现运营后台页面、Enrollment 通用管理、TaskDefinition 配置后台或任意状态编辑；
- 未实现飞书 OAuth/回调、Reviewer/Operator 非本地外部身份绑定；ExternalIdentity 本次只记录邀请确认来源；
- 未实现旧数据导入、旧路由、旧 session/token 兼容、生产部署或发布操作；
- 未扩展 walking skeleton 的任务、提交、评审、结果业务规则。

## 6. 尚未运行的门禁

以下保持 `NOT_RUN`，不能由本地自动化替代：

- `AT-UAT-003` 真实新人邀请/身份异常恢复，以及真实 Operator/QA Recorder 证据；
- staging/production 独立 identity app、secret store、域名、TLS/cookie、反向代理真实 client address 与 ACL 审计；
- Reviewer/Operator 飞书身份绑定与真实账号权限矩阵；
- 生产 rate-limit/告警、会话撤销传播窗口、备份恢复、回滚和发布签字；
- G4/G5 真实标准路径、试点与观察窗口。

因此当前结论是：`WP-01 LOCAL BUILD VERIFIED`，不是 `UAT PASSED`、`RELEASE GO` 或 `PRODUCTION READY`。
