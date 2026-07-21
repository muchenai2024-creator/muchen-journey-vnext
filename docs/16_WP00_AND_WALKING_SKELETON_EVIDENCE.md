# 16｜WP-00 与 Walking Skeleton 构建证据

状态：`AS_BUILT`  
版本：V0.1  
日期：2026-07-20  
验证环境：本地 Docker Compose，未发布  
Owner：Liu Mowen（初始 Product + Tech Owner）

## 1. 本次完成范围

- 将 00–15 号批准文档迁入独立 Git 仓库，与实现共同版本化；
- 建立独立 Web、API、Worker、PostgreSQL、CI、配置示例和容器基座；
- 建立从空库开始的 `0001_initial` migration 与本地受控 fixture seed；
- 实现唯一 TSK-001 标准路径：当前行动 → 开始 → 文本提交 → 主管队列/固定版本 → Rubric finalize → `HANDOFF_READY`；
- 实现 revision 冲突、Idempotency-Key、事务 outbox、组织/显式角色 scope、请求 ID、统一错误和安全响应头；
- Web 只消费服务端业务状态与 allowed commands，不建立第二套前端状态机。

## 2. 机器证据

| 证据 | 2026-07-20 结果 |
| --- | --- |
| `make api-test` | `10 passed`；从空测试库执行 downgrade/upgrade/seed 后覆盖标准闭环、权限、版本冲突、幂等重放/误用、Rubric 不变量和 fixture fail-closed |
| `make web-check` | ESLint、TypeScript 与 Next.js production build 全部通过；7 个产品路由成功生成 |
| `npm audit --audit-level=moderate` | `found 0 vulnerabilities` |
| `make isolation-check` | `isolation checks passed`；无旧源码/运行时引用、无 submodule、migration 从 0001 开始 |
| `docker compose up --build --wait` | DB、API、Worker、Web 启动成功；DB/API 健康检查通过，API migration/seed 成功 |
| 容器 HTTP smoke | `/health/ready` 为 200；`/app` 为 200 且渲染“开始当前任务” |
| 安全头 smoke | API 有 request ID/nosniff/no-store；Web 有 nonce CSP、frame deny、permissions policy 与 nosniff |
| 机器合同 | [`contracts/openapi.json`](../contracts/openapi.json) 已由运行中的 API 生成 |

## 3. 当前明确不做

Walking skeleton 没有同时铺开以下 WP-01–06 完整模块：真实邀请/会话与飞书绑定、附件、运营后台、真实通知渠道、旧数据导入、完整审计后台、生产观测与发布编排。AI Advisor 仍不进入 P0。

本地 `X-Fixture-Role` 只允许 `APP_ENV=local/test` 且显式开启；staging/production 同时配置 fixture 身份会在启动时失败。它不是生产身份实现。

## 4. 尚未运行的发布门禁

以下均为 `NOT_RUN`，不能由本地自动化结果替代：

- 5 名真实 Learner、2 名独立 Reviewer、Operator 与 QA Recorder 的受控名册和 UAT；
- Reviewer 三类样本真人校准与 Learner 首次任务理解测试；
- 独立 staging/production DB、bucket、identity app、secret store、域名、CI 身份、日志/APM 的物理 ACL 证明；
- 备份恢复、回滚、告警、事故值守和双人发布批准演练；
- 14 天真实试点 KPI 与停止护栏。

因此当前结论是：`LOCAL BUILD VERIFIED`，不是 `RELEASE GO` 或 `PRODUCTION READY`。
