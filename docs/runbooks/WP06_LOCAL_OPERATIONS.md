# WP-06 本地运营、备份恢复与发布门禁 Runbook

状态：仅限本仓库 Greenfield Compose `local/test`。本文不授权 staging/production、真实外部通知、物理 ACL、生产迁移、生产备份删除/恢复或发布签署。

## 1. 不可跨越的边界

- 唯一数据目标是 Compose 的 `journey_next_dev` 与临时 `journey_next_test`；工具没有非本地 target 参数。
- Enrollment 只能通过 create/join、assign reviewer、cancel 等有业务语义的命令变更，不提供通用 status/SQL editor。
- reviewer 只有在 Review 尚未生成时可重分配；存在任何 Review 时拒绝改写事实。
- 旧系统导入依 `DEC-009` 保持 `NOT_RUN`。本地 importer 只接受签名的 `SYNTHETIC_VNEXT_FIXTURE` 包，不联网、不写回来源。
- 本地备份使用 owner-only key 与 AES-256-CBC/PBKDF2；key 和工件均被 Git 忽略。本地加密与同机恢复不能替代异机副本、KMS、生产备份恢复。
- 发布门禁缺项、`FAIL` 或 `NOT_RUN` 一律 `NO_GO`；真人 UAT、真实外部通知、staging/production、物理 ACL、异机恢复、发布批准和真实观察窗没有运行时，不允许 GO。

## 2. 备份前检查

1. 确认 `docker compose ps` 中仅本仓库服务；确认数据库名为 `journey_next_dev`。
2. 完整检查 `scripts/wp06_ops.py`，确认没有 production/staging target、网络写回或宽泛删除。
3. 运行 `make verify`；记录失败与重试，不得用备份掩盖失败。
4. 运行 `make wp06-backup`。输出目录为 `artifacts/wp06/wp06-*/`，权限为 0700，文件权限为 0600。
5. 检查 `backup-manifest.json` 的 scope、migration、TaskVersion 指纹、计数、checksum/HMAC 和明确 `NOT_RUN`。

## 3. 隔离恢复与回滚演练

`make migration-check` 先在独立库写入 0009 合成基线，再执行 `0009 → 0010 → 0009 → 0010` 并逐次比较业务指纹。历史 schema 无法表达后期合法终态，因此不把含后期事实的数据库一路强制回退到 base；空库完整链路由 `api-test` 每次精确重建 `journey_next_test` 后执行 `base → head` 证明。

1. 运行 `make wp06-drill`。工具验证 manifest HMAC、密文 checksum、解密后 checksum。
2. 工具只在 `db-test` 创建 `journey_next_restore_<8 hex>`；目标已存在即拒绝，绝不覆盖。
3. `pg_restore --exit-on-error` 后比较迁移 head、表计数、TaskVersion 指纹、约束和关键跨组织/对象不变量。
4. 在同一隔离库执行 `0010 → 0009 → 0010`，再次比较全部业务指纹。
5. 证据写入 `restore-rollback-report.json`，随后只删除精确的临时恢复库。开发库与测试基准库不被修改。
6. 任一步失败：停止；保留工件和 stderr；修复候选后从新备份重新演练，不把失败报告改写为 PASS。

## 4. 告警模拟

`make wp06-alert-sim` 运行健康与故障合成输入，必须分别得到无告警，以及 worker stale、outbox backlog、dead delivery、release mismatch、migration mismatch。该演练不发送真实 Pager/Feishu/邮件；真实外部告警投递保持 `NOT_RUN`。

## 5. 发布门禁

- `make release-gate-check` 验证当前证据必须得到预期 `NO_GO`，命令返回 0 供本地自动化使用。
- `make release-gate` 是实际发布判定；当前因外部门禁 `NOT_RUN` 返回非零 3，从而阻止发布。
- 只有绑定同一冻结候选的真实证据才能把某项改为 `PASS`。本地模拟、fixture、Compose 和 Chromium 自动化不得冒充真人批准、真实通知或物理环境证明。

## 6. 处置与恢复

- 备份或恢复 checksum/HMAC 失败：隔离工件，不尝试容错导入。
- 迁移回退/再升级失败：保留临时库（若工具已清理则从同一备份重建），停止候选；优先 forward fix，不修改历史数据以迎合旧 schema。
- worker stale/backlog/dead：保持业务结果事实，暂停消费者、查 revision/lease/adapter；不得通过改业务状态清队列。
- 权限泄露或 object scope 异常：停止相关入口，保留审计，撤销本地 session/secret，完整跑 HTTP 权限负向矩阵。

## 7. 明确 NOT_RUN

真人 Learner/Reviewer/Operator UAT；真实 Feishu/邮件/告警投递；staging/production 部署与迁移；物理 DB/对象存储 ACL；异机/生产备份创建和恢复；真实流量、观察窗、值守与发布签署；旧系统真实数据导出/导入。
