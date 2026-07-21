# 07｜API、事件与集成合同

状态：`APPROVED_FOR_BUILD`  
版本：V0.1  
日期：2026-07-20  
文档 Owner：Tech Lead  
合同目标：P0 开工前冻结资源、命令、状态、错误、幂等和外部集成边界；实现以 OpenAPI/JSON Schema 为机器事实源。

## 1. 通用约定

- Base path：`/api/v1`；
- JSON 字段使用 `snake_case`（若选其他规范需全局统一）；
- 时间使用 UTC RFC 3339，展示层本地化；
- ID 使用不泄露计数的 UUID/ULID；
- GET 无副作用；写入使用意图明确的 command endpoint；
- 不提供通用 `PATCH status`；
- 受保护响应默认 `Cache-Control: no-store`；
- 所有响应包含 `request_id`；
- 写命令需要 `Idempotency-Key` 和/或 `expected_revision`；
- 旧 API、旧 token 和旧错误码不兼容。

## 2. 会话与身份

| Method | Path | 目的 |
| --- | --- | --- |
| POST | `/join/exchange` | 验证一次性邀请并建立最小加入上下文 |
| POST | `/identity/confirm` | 确认/绑定 vNext 内部身份 |
| GET | `/session` | 返回当前用户、角色、scope 和安全入口 |
| POST | `/session/logout` | 撤销当前会话 |

非本地会话使用 Secure、HttpOnly、SameSite cookie。身份方案按 `DEC-006` 使用邀请建立 vNext 内部身份，并为 Reviewer/Operator 绑定独立飞书身份；接口只返回内部 user id，不向业务域传播第三方 token。

## 3. Learner 读取与命令

| Method | Path | 目的 | 关键语义 |
| --- | --- | --- | --- |
| GET | `/me/current-action` | 唯一当前行动 | 由服务端 resolver 返回 |
| GET | `/me/assignments/{id}` | 任务详情 | 仅本人；含 task version 与 allowed commands |
| POST | `/me/assignments/{id}/start` | 开始任务 | expected revision；幂等 |
| POST | `/me/assignments/{id}/submissions` | 首次/修订提交 | 固定正文与附件版本；幂等 |
| GET | `/me/submissions/{id}` | 当前与历史提交 | 正文按权限；历史只读 |
| GET | `/me/result` | 当前结果和下一步 | 来源 Evaluation 可追溯 |
| GET | `/me/timeline` | 只读业务时间线 | 游标分页；不返回敏感内部事件 |

## 4. 附件

| Method | Path | 目的 |
| --- | --- | --- |
| POST | `/attachments/presign` | 创建受控上传意图 |
| POST | `/attachments/{id}/complete` | 校验 hash/size/type 并标记待扫描/READY |
| DELETE | `/attachments/{id}` | 删除未绑定或允许移除的附件 |
| GET | `/attachments/{id}/download` | 再授权后返回短时下载 URL/流 |

上传意图绑定 owner、purpose、最大尺寸和允许类型。未 READY、跨 owner、跨 organization 或 purpose 不匹配的附件不能进入 SubmissionVersion。

## 5. Reviewer

| Method | Path | 目的 | 关键语义 |
| --- | --- | --- | --- |
| GET | `/reviews` | 授权评审队列 | 按 scope 与优先级；游标分页 |
| GET | `/reviews/{id}` | 固定版本详情 | GET 无副作用 |
| POST | `/reviews/{id}/start` | 开始/领取评审 | 明确 reviewer；并发安全 |
| POST | `/reviews/{id}/finalize` | 提交人工结论 | Rubric 完整；expected revision；幂等 |

`finalize` 只允许 `PASS` 或 `REVISION_REQUIRED`（P0）；AI 建议不能作为 final actor。

## 6. Operator/Admin

| Method | Path | 目的 |
| --- | --- | --- |
| GET/POST | `/ops/invites` | 查询/创建邀请 |
| POST | `/ops/invites/{id}/revoke` | 撤销邀请，要求 reason |
| GET | `/ops/enrollments` | 查询授权范围 Enrollment |
| PUT | `/ops/enrollments/{id}/reviewer` | 分配/更换 reviewer，记录前后值与理由 |
| POST | `/ops/enrollments/{id}/cancel` | 受控取消，要求 reason |
| GET/POST | `/ops/task-definitions` | 创建草稿/查看任务定义 |
| POST | `/ops/task-definitions/{id}/publish` | 发布不可变 TaskVersion |
| GET | `/ops/audit` | 按权限查询审计元数据 |

不开放任意字段编辑、SQL 控制台或“修复 status”接口。新的纠错需求必须增加有业务语义的命令。

## 7. Current Action 示例

```json
{
  "data": {
    "action_type": "REVISE_SUBMISSION",
    "resource_id": "01...",
    "title": "根据主管反馈修订任务",
    "reason": "上一版需要补充交付依据",
    "allowed_commands": ["submit_revision"],
    "revision": 7
  },
  "request_id": "req_..."
}
```

页面不得再请求旧状态接口进行拼接。

## 8. 错误合同

统一包络：

```json
{
  "error": {
    "code": "VERSION_CONFLICT",
    "message": "任务状态已更新，请确认最新内容后重试。",
    "details": {},
    "retryable": false
  },
  "request_id": "req_..."
}
```

| HTTP | code | 用途 |
| --- | --- | --- |
| 400 | `INVALID_REQUEST` | 结构/语义无效 |
| 401 | `UNAUTHENTICATED` | 无有效 vNext 会话 |
| 403 | `FORBIDDEN` | 身份有效但无权限 |
| 404 | `NOT_FOUND` | 资源不存在或需隐藏存在性 |
| 409 | `VERSION_CONFLICT` | expected revision 过期 |
| 409 | `INVALID_STATE_TRANSITION` | 当前状态不允许命令 |
| 409 | `IDEMPOTENCY_KEY_REUSED` | 同 key 不同 request |
| 410 | `INVITE_EXPIRED_OR_REVOKED` | 邀请已不可用 |
| 413 | `ATTACHMENT_TOO_LARGE` | 超过限制 |
| 422 | `VALIDATION_FAILED` | 业务必填/Rubric/材料不完整 |
| 429 | `RATE_LIMITED` | 限流，返回 retry-after |
| 503 | `DEPENDENCY_UNAVAILABLE` | 必要依赖不可用；不得假成功 |

错误码是协议的一部分，新增/修改需兼容评审和契约版本记录。

## 9. 幂等与并发

- start、submit、finalize、invite create、reviewer assignment 等命令携带 `Idempotency-Key`；
- 服务器保存 canonical request hash 和结果引用；
- 同 key + 同请求返回首次结果并标记 replay；
- 同 key + 不同请求返回 409；
- 对状态实体同时使用 `expected_revision`；
- finalize 在数据库唯一约束下保证每轮一个 final Evaluation；
- 客户端超时不得生成新 key 盲目重试；
- 幂等记录保留期限覆盖客户端/队列最大重试窗口，最终期限由 Data Owner 批准。

## 10. 领域事件

事件包络最小字段：

```json
{
  "event_id": "01...",
  "event_type": "submission.created.v1",
  "occurred_at": "2026-07-20T10:00:00Z",
  "organization_id": "01...",
  "aggregate_type": "assignment",
  "aggregate_id": "01...",
  "aggregate_revision": 3,
  "actor_id": "01...",
  "request_id": "req_...",
  "payload": {}
}
```

P0 事件：

- `invite.created.v1`、`invite.consumed.v1`、`invite.revoked.v1`；
- `identity.confirmed.v1`、`enrollment.activated.v1`；
- `assignment.started.v1`；
- `submission.created.v1`；
- `review.started.v1`、`review.finalized.v1`；
- `assignment.revision_requested.v1`、`assignment.completed.v1`；
- `outcome.created.v1`、`handoff.ready.v1`；
- `notification.requested.v1`。

事件是不可变事实通知，不是任意命令总线。敏感正文默认不进入事件 payload，只传引用和最小摘要。

## 11. 外部集成

### 飞书身份（如批准）

- 只处理 OAuth/企业身份映射；使用 vNext 独立 app/config/session；
- callback state 一次性、防重放、严格 return URL allowlist；
- 飞书 subject 只存在 Identity 模块。

### 飞书通知

- Worker 使用 vNext 独立凭证；
- recipient 来源于已验证身份/明确运营配置；
- 投递按 event + recipient + template version 幂等；
- 失败不更改业务状态；日志不打印 token/完整敏感正文。

### AI Advisor

- 异步、可超时、可禁用；
- 输入最小化、用途明确、记录 model/prompt/schema 版本；
- 输出只能写入 advisory record，不能调用 finalize；
- UI 标明建议、生成时间、不可用状态和人工责任。

### 旧系统

没有运行时 API 合同。唯一允许接口是离线导出包规范，见 11 号文档。

## 12. 契约验收

- `AT-API-001`：OpenAPI 与运行时路由/响应一致；
- `AT-API-002`：每个命令覆盖合法/非法状态、权限、幂等、并发；
- `AT-API-003`：GET 无副作用；
- `AT-API-004`：错误码、HTTP 状态和用户恢复动作一致；
- `AT-API-005`：事件 schema 可版本化，敏感字段审查通过；
- `AT-API-006`：飞书/AI 故障降级不污染业务事实；
- `AT-API-007`：API 定义中无旧路径、旧 token 和 compatibility adapter；
- `AT-API-008`：生成客户端与服务端合同 diff 为零。
