# 11｜发布、数据导入与运行计划

状态：`APPROVED_FOR_BUILD`  
版本：V0.1  
日期：2026-07-20  
文档 Owner：Release/Ops Owner + Data Owner  
关键区别：本轮没有“边运行边迁移旧系统”的 runtime migration；只有离线数据导出/导入和独立流量切换。

## 1. 发布原则

- vNext 从第一天在独立环境运行；
- 旧系统不参与 vNext build、deploy、health、readiness 或 rollback；
- 数据导入和流量切换是两个独立决定；
- 生产开放写入后，旧系统不得重新成为写入事实源；
- 回滚应用不回滚已经产生的新业务事实；
- 每次发布绑定 commit SHA、image digest、migration、contract、UAT 和签署证据；
- 日期服从门禁，不现场绕过或反复重试生产脚本。

## 2. 环境模型

| 环境 | 用途 | 数据 | 外部集成 | 发布权限 |
| --- | --- | --- | --- | --- |
| Local | 开发与快速测试 | 合成 fixture | mock/sandbox，仅非生产 | 开发者 |
| Test/CI | 自动化、空库重建 | 每次隔离创建 | stub/sandbox | CI |
| Staging | 集成、导入演练、UAT | 脱敏/专用 UAT | 独立飞书/存储/AI sandbox | 受限发布者 |
| Prod | 独立试点与正式运行 | 真实最小数据 | vNext 生产凭证 | 受限发布身份 + 审批 |

所有环境的域名、数据库、bucket、secret、队列、日志项目和 identity app 不得复用旧系统。

## 3. 发布工件

候选包至少包含：

- commit SHA、tag、构建时间、构建者；
- Web/API/Worker image digest 与 SBOM；
- OpenAPI/事件 schema 版本；
- migration head 与不可逆变更说明；
- 配置 schema 与 TaskVersion 清单；
- 测试/UAT/安全/隔离报告；
- 导入包版本与 checksum（如适用）；
- release notes、已知问题、回滚兼容范围；
- 批准人和生产窗口。

工件不可在部署服务器现场重新构建。

## 4. 历史数据导入

### 4.1 导入范围

默认只导入 P0 继续运行必需的数据，最终由 `DEC-009` 确认：

- 活跃试点用户的最小身份映射；
- 当前有效邀请/Enrollment（若业务确需延续）；
- 已批准且仍有效的任务/Rubric 内容；
- 仍在进行的必要 Assignment/Submission/Review；
- 依法/业务需要保留的最终结果引用。

不默认导入：测试、重复、无法解释状态、旧页面配置、旧日志副本、旧投影、浏览器状态、旧通知队列、旧 AI 输出、历史兼容字段。

### 4.2 中性导出包

旧系统侧只负责生成离线工件：

```text
manifest.json
schema/
  users.schema.json
  enrollments.schema.json
  work_items.schema.json
data/
  users.ndjson
  enrollments.ndjson
  work_items.ndjson
attachments/
checksums.sha256
source-report.json
signature
```

manifest 包含 source revision、导出时间、Owner、过滤范围、schema version、行数、附件数、PII 分类和 checksum。导出完成后工件只读。

### 4.3 vNext Importer

步骤：

1. 验证签名/checksum/schema；
2. 生成 dry-run：将创建、匹配、拒绝、歧义的数量；
3. Data/Product 对 quarantine 明确裁决；
4. 用 `import_batch_id` 和 source key 幂等导入；
5. 校验计数、唯一约束、外键、状态不变量和抽样业务事实；
6. 生成不可变 import report；
7. 重放同一包必须无重复；
8. 不向旧系统写回 import id 或新状态。

禁止 importer 在线查询旧 API/DB 来“补齐缺失字段”。

## 5. 试点与流量切换

### Phase A｜独立内部环境

只有合成/UAT 数据；证明 vNext 自己可运行。

### Phase B｜独立真实试点

使用 vNext 专属邀请/域名/账号，选择全新或明确划分的参与者；旧系统不同时承载同一参与者同一闭环。试点问题在 vNext 修复，不回补旧系统。

### Phase C｜目标批次切换

按 `DEC-010` 满足观察阈值后，新目标批次只进入 vNext。旧系统对这些对象只读，不允许继续写。

### Phase D｜正式入口切换

外部 DNS/网关/链接指向 vNext canonical 入口。旧链接由外部静态说明/410 处理，不在 vNext 加入 legacy 业务路由。

### Phase E｜旧系统归档/退役

在数据保留、审计、支持和法律要求满足后独立执行；不与 vNext P0 开发混在一个候选。

## 6. Preflight

- [ ] release SHA、tag、image digest 与批准候选一致；
- [ ] 工作树/构建工件干净且可验证；
- [ ] prod env schema 完整；旧 secret/endpoint 不存在；
- [ ] DB 连接指向 vNext 独立数据库，role 最小权限；
- [ ] migration dry-run 与当前 head 一致；
- [ ] 对象存储、身份回调、飞书通知、AI（如启用）属于 vNext；
- [ ] 备份成功且最近一次隔离恢复演练有效；
- [ ] UAT、隔离、安全、性能和发布签字通过；
- [ ] 观察仪表盘、告警、值守和沟通已准备；
- [ ] 唯一 RC 未漂移；生产窗口内没有第二候选。

Preflight 只读。任何检查需要“顺便修配置/改数据库”时停止发布，回到候选流程。

## 7. 部署顺序

1. 记录 Release ID、revision、工件和责任人；
2. 获取 vNext DB 备份/快照；
3. 执行 migration runner（独立身份）；
4. 部署 API/Worker/Web 的兼容顺序；
5. readiness/liveness 通过后运行封闭 smoke；
6. 验证 release revision、DB head、contracts、worker 和指标；
7. 开放专用试点/目标批次流量；
8. 进入观察窗口；
9. 达到退出条件后签署完成，否则停止/回滚。

## 8. 观察窗口

至少观察：

- 登录/加入成功率与异常邀请；
- Current Action 获取成功率/延迟；
- start/submit/finalize 成功、409、重复 replay；
- 权限拒绝和跨范围探测；
- outbox backlog、通知 RETRY/DEAD、AI 降级；
- DB 连接/锁/慢查询、对象存储失败；
- Web/API error rate 和关键页面性能；
- 真实支持介入、状态冲突、重复事实；
- release revision 是否一致。

观察时长和阈值由 `DEC-010/013` 确认。没有真实流量和责任人签字，不能仅凭健康检查结束观察。

## 9. 回滚与故障处置

### 9.1 允许的回滚

- Web/API/Worker 回滚到已验证且与当前 schema 兼容的上一 vNext release；
- 切换到 vNext 维护模式，停止新写，保留读/支持；
- 对可前滚修复的问题创建新候选；
- 使用受审计补偿命令修复明确事实。

### 9.2 禁止的回滚

- 恢复旧系统业务写入；
- 把新事实抄回旧表；
- 用发布前 DB 备份覆盖已经产生真实写入的 vNext 数据库；
- 现场修改容器/数据库/环境绕过版本控制；
- 关闭权限/幂等/迁移/备份门禁继续放量。

### 9.3 故障卡

| 故障 | 第一动作 | 恢复证明 |
| --- | --- | --- |
| DB 不可用/高延迟 | 停写/维护；保护事务；查连接、锁、容量 | health、关键读写、约束、备份 |
| 登录/邀请广泛失败 | 停新加入；查 vNext identity/callback/clock | 新/已有用户、重放、回调、会话 |
| 重复提交/结论 | 立即停相关命令；保留证据；查幂等/约束 | 唯一事实、补偿、全矩阵回归 |
| 权限泄露 | 停相关入口/写入；撤销 session/secret；事故响应 | 正/负向权限、日志、影响范围 |
| 通知/AI 故障 | 保持业务；暂停消费者或进入重试 | 业务事实正确；backlog 恢复且不重复 |
| 前端故障 API 正常 | 回滚上一 vNext Web/维护页 | 三视口、主路径、revision 一致 |
| 导入差异 | 不开放流量；保留包/批次；quarantine | dry-run/重放/计数/抽样全解释 |

## 10. 备份与恢复

需由 `DEC-013` 明确 RPO/RTO。最低合同：

- 自动备份 + 独立/异机副本；
- 备份加密、owner-only/最小访问；
- checksum、manifest、schema/release 元数据；
- 定期在空白隔离环境恢复，不对生产目标演练；
- 恢复后验证 migration head、计数、唯一/外键、关键聚合指纹和样本闭环；
- 非空目标默认拒绝恢复；
- 恢复证据有时间、Owner、工件和结论。

## 11. Go / No-Go

### 必须 No-Go

- 任何 ISO-MUST 不满足；
- Sev-1/Sev-2 未关闭；
- RC/revision/image/migration 不一致；
- 真实 UAT 未通过或以 mock 替代；
- 备份恢复、权限、幂等、数据核对失败；
- 旧系统仍需在线/可写才能完成 vNext 流程；
- 导入存在未解释差异；
- 无明确值守、回滚和观察 Owner。

### Go 条件

- 所有发布门禁通过且绑定同一候选；
- 真实标准/修订路径通过；
- 数据、权限、安全、运行、业务签字完整；
- 观察阈值和停止条件明确；
- 旧系统只读边界已确认。

## 12. As-Built 规则

发布后创建独立的 As-Built 记录，包含实际 topology、revision、migration、配置、导入批次、UAT、观察、事故和偏差。不得把生产事实直接追加进原架构/PRD V0.1 并继续把它称为开发前基线。
