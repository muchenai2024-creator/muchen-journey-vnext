# 05｜领域模型、状态机与数据合同

状态：`APPROVED_FOR_BUILD`  
版本：V0.1  
日期：2026-07-20  
文档 Owner：Tech Lead + Data Owner  
原则：新模型从业务事实推导，不从旧表、旧 JSON、旧 API 或旧枚举翻译而来。

## 1. 领域边界

P0 使用一个模块化单体中的七个清晰模块：

| 模块 | 责任 | 不负责 |
| --- | --- | --- |
| Identity | 内部用户、外部身份、会话、角色 | 业务阶段和评审结论 |
| Enrollment | 邀请、加入、批次、主管分配 | 任务正文和评分 |
| Learning Work | 任务定义、个人 Assignment、提交版本、附件 | 人工最终结论 |
| Review | 授权队列、开始评审、评价与结论 | 代替学员提交 |
| Outcome | 结果、交接和下一步 | 修改历史评审 |
| Notification | 发送计划、重试、交付结果 | 决定业务成功与否 |
| Governance | 审计、幂等、运营命令、配置发布 | 通用数据库直接编辑 |

P0 不拆成微服务；模块通过明确接口和数据库约束隔离。未来是否拆分必须由真实负载或团队边界驱动，不做预留式分布式架构。

## 2. 核心实体

| 实体 | 核心字段 | 不变量 |
| --- | --- | --- |
| `Organization` | id, name, status | P0 即使单组织也显式隔离 |
| `User` | id, organization_id, status | 内部 UUID；不使用飞书 open_id 作为主键 |
| `ExternalIdentity` | provider, subject, user_id, verified_at | provider + subject 全局/组织内唯一 |
| `RoleAssignment` | user_id, role, scope, valid_from/to | 权限有范围和有效期 |
| `Invite` | id, token_hash, purpose, expires_at, status | 存哈希不存明文 token；消费/撤销原子 |
| `Enrollment` | id, organization_id, learner_id, cohort_id, reviewer_id, status, revision | learner + active program 唯一 |
| `TaskDefinition` | id, stable_key | 只是稳定身份，不含可变内容 |
| `TaskVersion` | task_id, version, content, rubric, published_at | 发布后不可变；Assignment 固定引用版本 |
| `Assignment` | id, enrollment_id, task_version_id, status, revision | 一个 Enrollment 同一任务最多一个有效实例 |
| `Submission` | id, assignment_id, current_version_no | 容器；当前版本号单调递增 |
| `SubmissionVersion` | submission_id, version_no, body, created_by/at | 不可变；唯一 `(submission_id, version_no)` |
| `Attachment` | id, owner_id, storage_key, hash, scan_status | READY 且授权匹配才可绑定提交 |
| `Review` | id, assignment_id, submission_version_id, reviewer_id, status, revision | 固定引用一个提交版本；每轮只有一个有效 final |
| `Evaluation` | review_id, decision, rubric_scores, feedback | final 后不可变；人工责任人明确 |
| `Outcome` | enrollment_id, source_evaluation_id, status, next_step | 只能由有效 Evaluation 产生 |
| `NotificationDelivery` | event_id, recipient, channel, status, attempts | 不拥有业务事实；按 event/recipient/channel 幂等 |
| `DomainEvent` | id, type, aggregate, payload_version, occurred_at | append-only；消费者按 event id 幂等 |
| `AuditEntry` | actor, action, resource, result, request_id, occurred_at | append-only；敏感正文最小化 |
| `IdempotencyRecord` | actor, command, key, request_hash, response_ref | 同 key 不同请求必须拒绝 |

## 3. 权威状态机

### 3.1 Invite

```text
DRAFT → ACTIVE → CONSUMED
          ├──→ REVOKED
          └──→ EXPIRED
```

- 只有 ACTIVE 可消费；
- CONSUMED/REVOKED/EXPIRED 为终态；
- 过期由时间判断并持久化/投影，不在前端发明状态；
- token 只显示一次，数据库存哈希。

### 3.2 Enrollment

```text
PENDING_IDENTITY → ACTIVE → COMPLETED
        │            └──→ CANCELLED
        └────────────────→ CANCELLED
```

Enrollment 只表达加入生命周期。等待评审、需要修订等属于当前 Assignment，不在 Enrollment 复制一套同义状态。用户首页由 Current Action Resolver 组合权威实体后返回单一 action。

### 3.3 Assignment

```text
AVAILABLE → IN_PROGRESS → SUBMITTED → IN_REVIEW
                  ↑                       │
                  └── NEEDS_REVISION ←────┤
                                          └──→ COMPLETED

AVAILABLE / IN_PROGRESS / NEEDS_REVISION / SUBMITTED → CANCELLED（受控运营命令）
```

允许命令：

| 当前状态 | 命令 | 下一状态 | 关键约束 |
| --- | --- | --- | --- |
| AVAILABLE | start | IN_PROGRESS | owner 本人；expected revision |
| IN_PROGRESS | submit | SUBMITTED | 创建不可变 SubmissionVersion；附件 READY |
| NEEDS_REVISION | submit_revision | SUBMITTED | version_no + 1；旧版本不变 |
| SUBMITTED | start_review | IN_REVIEW | 明确 reviewer；固定 submission version |
| IN_REVIEW | finalize_revision | NEEDS_REVISION | Evaluation 原子写入 |
| IN_REVIEW | finalize_pass | COMPLETED | Evaluation + Outcome/next action 原子或可恢复 |

禁止从 `SUBMITTED` 直接变 `COMPLETED`；禁止覆盖 final Evaluation；禁止前端 PATCH 任意 status。

### 3.4 Review

```text
ASSIGNED → IN_REVIEW → FINALIZED
    └───────────────→ CANCELLED（仅受控重分配/撤销）
```

GET review detail 无副作用。只有 `start` 命令能改变状态。FINALIZED 不能通用 reopen；纠错需要独立的撤销/替代流程及批准，P0 默认不开放。

### 3.5 NotificationDelivery

```text
PENDING → SENDING → DELIVERED
              └──→ RETRY_WAIT → SENDING
              └──→ DEAD
```

通知失败不改变 Assignment、Review、Evaluation 或 Outcome。

## 4. Current Action Resolver

服务端用确定优先级返回一个 `CurrentAction`，前端只渲染：

1. 无有效身份 → `CONFIRM_IDENTITY`；
2. Enrollment 非 ACTIVE → `RESOLVE_ENROLLMENT` 或完成说明；
3. 当前 Assignment NEEDS_REVISION → `REVISE_SUBMISSION`；
4. AVAILABLE/IN_PROGRESS → `START_OR_CONTINUE_TASK`；
5. SUBMITTED/IN_REVIEW → `WAIT_FOR_REVIEW`；
6. COMPLETED 且有下一 Assignment → 下一任务；
7. COMPLETED 且无下一 Assignment → `VIEW_RESULT_OR_HANDOFF`。

响应包含：`action_type`、`resource_id`、`title`、`reason`、`allowed_commands`、`revision`。不返回旧状态映射或兼容 fallback。

## 5. 事务与一致性

- start、submit、start_review、finalize 使用数据库事务和行级/乐观并发控制；
- `expected_revision` 不一致返回 409，不自动覆盖；
- command 成功与 DomainEvent/outbox 写入同一事务；
- 通知、分析和非关键投影异步处理；
- 同一业务命令通过 `(actor, command, idempotency_key)` 唯一；
- finalized review 与 Evaluation 唯一；
- Outcome 必须引用产生它的 Evaluation；
- 所有外键包含组织范围校验或通过约束/服务层保证不跨组织。

## 6. 数据所有权

| 事实 | 唯一 Owner | 投影/消费者 |
| --- | --- | --- |
| 用户与外部身份 | Identity | UI、审计、通知 |
| 邀请与 Enrollment | Enrollment | Current Action、运营看板 |
| 当前任务状态 | Assignment | UI、Review、分析 |
| 提交正文与版本 | SubmissionVersion | Review、历史 |
| 评审过程 | Review | 队列、分析 |
| 最终人工结论 | Evaluation | Outcome、UI、分析 |
| 结果与下一步 | Outcome | Learner UI、通知 |
| 通知结果 | NotificationDelivery | 运营、告警 |
| 审计 | AuditEntry | 安全、运营 |

飞书、浏览器、本地缓存、分析仓库和导入文件都不是业务 Owner。

## 7. 数据分类与保留

最终期限由 `DEC-008` 批准。在批准前采用最小化默认：

| 类别 | 示例 | 默认控制 |
| --- | --- | --- |
| 身份标识 | 姓名、手机号、飞书 subject | 加密传输、最小访问、日志脱敏 |
| 任务正文/附件 | 新人提交材料 | 对象级授权、病毒/类型检查、短时下载链接 |
| 评价与结果 | Rubric、反馈、结论 | Learner/Reviewer/授权运营可见；审计访问 |
| 安全数据 | session、invite token、secret | 只存哈希/密钥系统；永不进日志/分析 |
| 运营元数据 | 状态、时间、request id | 可用于运行与聚合分析 |

访问到期、账号停用、数据删除和审计保留是不同状态，不能互相替代。

## 8. 历史数据导入边界

- 只导入 Product/Data 明确列出的活动参与者、必要身份映射、有效任务配置和仍需继续的当前事实；
- 不按旧表 1:1 搬运，不导入测试/重复/不可解释状态；
- 旧状态先导出为原始中性字段，由显式规则转换；无法唯一映射的记录进入 quarantine；
- vNext 导入器只读本地/对象存储中的签名数据包，不连接旧生产系统；
- 每次导入生成 source checksum、规则版本、计数、拒绝原因和抽样报告；
- 导入后不向旧系统写回。

## 9. Schema 开发前交付物

- [ ] 逻辑 ERD 与组织边界；
- [ ] 每张表的主键、唯一约束、外键、索引和敏感级别；
- [ ] 状态枚举及迁移矩阵；
- [ ] Current Action Resolver 决策表；
- [ ] P0 seed/config 版本策略；
- [ ] 数据保留/删除/匿名化决定；
- [ ] 一次性导出格式和 quarantine 格式；
- [ ] 空库 `0001_initial` 迁移审查；
- [ ] 数据不变量与属性测试清单。

## 10. 数据验收

- `AT-DATA-001`：空库迁移和回滚/前向修复策略通过；
- `AT-DATA-002`：全部合法/非法状态迁移均测试；
- `AT-DATA-003`：重复提交、并发 finalize 只产生一个事实；
- `AT-DATA-004`：跨组织/跨用户外键和读取被拒绝；
- `AT-DATA-005`：历史版本不可变且可追溯；
- `AT-DATA-006`：通知失败不污染业务事务；
- `AT-DATA-007`：离线导入可重放且拒绝项不自动修正；
- `AT-DATA-008`：备份恢复后 schema、计数、约束和业务指纹一致。
