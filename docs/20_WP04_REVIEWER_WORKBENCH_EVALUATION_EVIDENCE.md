# 20｜WP-04 Reviewer 工作台与结论构建证据

状态：`AS_BUILT`  
版本：V0.1  
日期：2026-07-21  
验证环境：本地 Docker Compose，未发布  
Owner：Liu Mowen（初始 Product + Tech Owner）

## 1. 开工 Gap Audit

本工作包先完整读取 README、00、03、04、05、06、07、08、09 V0.2、10 V0.2、12、13、14、15、16、17、18、19，并按批准合同重新审计 walking skeleton。结论是已有 `/review`、`Review/Evaluation` 与 start/finalize 只够作回归基线，不能关闭 `REQ-BR-005`：

| 批准要求 | 开工时事实 | WP-04 As-Built | 主要证据 |
| --- | --- | --- | --- |
| Reviewer 队列与对象授权 | 队列只有 learner/task/status；Reviewer 主要依赖单一 ID 条件 | 队列与详情同时约束 explicit reviewer、organization、Assignment、Submission、Enrollment、Learner、TaskDefinition、TaskVersion；同组织其他 Reviewer 与跨组织对象均返回 404 | `test_queue_detail_scope_priority_and_get_are_side_effect_free`；最终 HTTP 403/404 |
| GET 无副作用 | 路由看似只读，但没有记录级证明 | 两次 queue/detail GET 前后 Review 状态/修订/时间戳及 Evaluation/Audit/Outbox/Review 计数完全不变 | GET side-effect 自动化 |
| 固定材料与 Rubric | 详情只给正文与宽松 rubric；没有附件完整性、交付要求或每维反馈 | 固定 TaskVersion、SubmissionVersion、正文、附件状态、缺失项、required deliverables 和四个 rubric 维度共同呈现；材料不完整时服务端拒绝 finalize | material API/UI/422 测试 |
| 结构化最终结论 | 旧 finalize 接收 scores map、自由文本和 PASS/REVISION_REQUIRED | 命令固定 `APPROVE`/`REQUEST_REVISION`；恰好四个维度均需 rating + 5–500 字反馈，总体反馈 10–2000 字；决策和评分一致性由服务端验证 | strict Pydantic、OpenAPI、422 负向测试、最终 Playwright |
| 并发与重放 | 通用幂等骨架存在，但 resource ID 未进入 payload hash，也没有并发 finalize 证明 | request hash 包含 Review ID；Review/Assignment 行锁 + expected revision；不同 key 并发一成功一 409，同 key 并发 200/200 replay 且只有一个 Evaluation；同 key 异 payload 明确 409 | ThreadPool API 测试 |
| 结论不可变与固定引用 | Evaluation 只固定 review_id，应用可 UPDATE/DELETE；旧结论存在覆盖空间 | Evaluation 固定 organization/assignment/submission/submission_version/reviewer/review_revision；复合 FK/check/unique；DB trigger 拒绝 Evaluation UPDATE/DELETE 与 finalized Review 改写/删除 | `0007_reviewer_workbench`；直接 SQL 负向测试 |
| 状态闭环 | skeleton 能产生最小结果，但页面没有真实评审工作流 | `ASSIGNED/SUBMITTED → IN_REVIEW/IN_REVIEW → FINALIZED/NEEDS_REVISION|COMPLETED` 原子迁移；Web 完成队列→详情→开始→四维反馈→结论；Learner 立即看到等待/修订状态 | API 状态测试；双会话最终 Playwright |
| 旧历史兼容 | 旧 Evaluation 没有结构化反馈或完整 scope | 迁移补齐可证明的固定 scope 与 review revision，但不伪造维度反馈；标记 `feedback_structure_version=0`，UI 明示旧版未记录 | 持久库升级与 legacy 输出逻辑 |

`muchen-journey-ops:operate-muchen-journey` 的 doctor 先因误用不存在的仓库内脚本路径以 exit 2 失败；改用技能实际 helper 后返回 `Not a compatible Muchen Journey repository`。按技能要求没有创建第二套脚本，后续只使用本仓库既有 Make targets、Compose、curl 和 Playwright。

## 2. 实际实现合同

### 2.1 Review、Evaluation 与历史

- `Review` 明确固定 `organization_id`、`assignment_id`、`submission_id`、`submission_version_id` 和 `reviewer_id`，并记录 assigned/started/finalized 时间；复合外键阻止跨组织、跨 Assignment 或跨 SubmissionVersion 拼接。
- Review 只允许 `ASSIGNED → IN_REVIEW → FINALIZED`，revision 每次只加一；数据库 trigger 拒绝跳转、固定引用变化、finalized 后更新以及历史删除。
- `Evaluation` 在 finalize 时一次写入固定 scope、review revision、总体结论、总体反馈、四维 rating 与每维反馈；数据库 trigger 拒绝任何 UPDATE/DELETE。
- 既有 V0 Evaluation 仅回填可由旧引用证明的 scope，保留原 scores/feedback，`structured_feedback=NULL`、`feedback_structure_version=0`；没有把总体反馈复制成伪造的每维反馈。

### 2.2 队列、详情与材料完整性

- `GET /api/v1/reviews` 只返回显式分配给当前 actor 的未定稿 Review，并按“已开始、修订提交、等待时间”排序；每项返回固定版本、材料状态、优先原因和服务端 `allowed_commands`。
- `GET /api/v1/reviews/{id}` 在同一查询中约束 role、reviewer、organization 与全部对象链；越权对象统一 404，Learner role 为 403。GET 不创建 Review/Evaluation/Audit/Outbox，不改 revision 或时间戳。
- 材料完整性固定于当前 SubmissionVersion：正文至少满足提交合同，所有绑定附件必须 `READY + LOCAL_CLEAN`；响应包含 required deliverables、附件元数据和缺失项。材料不完整可开始核对，但不能 finalize。
- 详情同时展示固定 TaskVersion/SubmissionVersion、正文、完成标准、交付要求、固定引用与已有只读 Evaluation；finalized Review 不再出现在工作队列，但授权 Reviewer 仍可通过详情查看历史。

### 2.3 start、finalize、并发与状态

- `POST /reviews/{id}/start` 在幂等检查前先锁定并授权 Review，再锁 Assignment；仅允许 Review `ASSIGNED` 且 Assignment `SUBMITTED`，原子迁移为 `IN_REVIEW`。
- `POST /reviews/{id}/finalize` 要求完整四维 Rubric、维度级具体反馈、总体反馈和 overall decision。`APPROVE` 必须全为 `MEETS`；`REQUEST_REVISION` 至少一项为 `NEEDS_WORK`。
- `APPROVE` 映射持久结论 `PASS`，Assignment 进入 `COMPLETED`；`REQUEST_REVISION` 映射 `REVISION_REQUIRED`，Assignment 进入 `NEEDS_REVISION`。Learner allowed command 随后分别进入既有结果或 `submit_revision`。
- 同一 actor/command/key/Review/payload replay 返回首次结果并标记 `idempotency_replay=true`；同 key 异 payload 为 `IDEMPOTENCY_KEY_REUSED`；不同 key 或旧 expected revision 为 `VERSION_CONFLICT`。
- finalize 审计只保存 resource IDs、decision、Rubric 维度数和总体反馈字符数，不复制提交正文或反馈内容；事件正文只包含 aggregate ID。

### 2.4 Web 与工作包边界

- Next Server Component 读取队列/详情，Server Actions 转发 session cookie、CSRF 与稳定 idempotency key；client component 只持有表单 pending/error 和尚未提交的 input，不发 client fetch，不维护第二套状态机。
- 页面动作只由服务端 `allowed_commands` 决定；显示材料完整性、固定版本、四维评分/反馈、总体反馈、结论约束、局部错误/request ID 与 finalized 只读历史。
- Learner 页面复用 WP-03 的 `latest_revision_feedback`、历史和 `submit_revision`，可看到 WP-04 服务端产生的等待/修订状态。
- `APPROVE` 只保留 walking skeleton 已有的最小 `Outcome(status=HANDOFF_READY)` 兼容结果。没有扩展 WP-05 的完整 Outcome 历史、通知 outbox worker、跨域时间线，也没有实现 WP-06 运营、导入或生产运行。

## 3. 迁移与数据证明

### 3.1 空库 base↔head

最终 `make verify` 对测试库先执行 `0007 → base`，再执行 `base → 0001 → … → 0007`、seed 与全部测试；结果 `38 passed in 2.09s`。这证明空库升级、完整 downgrade/upgrade 顺序、最新 schema 与数据模型可执行。

### 3.2 WP-03 持久开发库升级

升级前只读快照：head=`0006_submission_attachments`，Organization=1、Invite=7、Assignment=4、TaskVersion=2、Submission=2、SubmissionVersion=4、Attachment=1、Review=4、Evaluation=2。

执行 `make migrate`（2.04 秒）和 `make seed`（1.63 秒）后：

- head=`0007_reviewer_workbench`；上述九项计数全部保持 1/7/4/2/2/4/1/4/2；
- `review_scope_mismatches=0`、`evaluation_scope_mismatches=0`；
- Invite、Assignment、TaskVersion、SubmissionVersion、Attachment 核心事实均保留；已有 Evaluation 只补可证明 scope，不生成新结论或结构化反馈。

最终自动浏览器随后按产品路径新增一个 Invite、Assignment、Submission/Version、Review 和 Evaluation；当前持久库计数相应为 1/8/5/2/3/5/1/5/3。这是明确的本地验收数据，不是迁移补写。该浏览器记录数据库复核为 Review `FINALIZED` revision 3、Assignment `NEEDS_REVISION`、SubmissionVersion 1、Evaluation `REVISION_REQUIRED`、4 条结构化反馈且固定 scope 全部匹配。

## 4. 自动化、安全与合同门禁

| 门禁 | 结果 |
| --- | --- |
| `make bootstrap` | 通过，6.83 秒；API/Worker build、Web `npm ci`，0 vulnerabilities |
| 变更前 API 基线 | `33 passed in 1.55s`，命令 7.31 秒 |
| 变更前 Web 基线 | ESLint、TypeScript、Next production build 通过，9.61 秒 |
| Reviewer 定向 API | 新增授权、GET 零写入、材料、结构化验证、不可变历史、APPROVE/REQUEST_REVISION、replay/conflict 与并发后 `38 passed in 2.15s`，命令 15.37 秒；scope 补强后再次 38 passed，15.40 秒 |
| Reviewer 定向 Web | ESLint、TypeScript、Next 16.2.10 production build 通过，6.56 秒 |
| 最终 `make verify` | `38 passed in 2.09s`；Web lint/type/build；`isolation checks passed`；总计 14.30 秒 |
| Python 依赖一致性 | `python -m pip check`：`No broken requirements found`，1.13 秒 |
| `npm audit --audit-level=moderate` | `found 0 vulnerabilities`，1.20 秒 |
| 最终 Compose | `docker compose up -d --build --wait` 候选镜像构建及 API/Web/Worker/DB/DB-test 健康等待通过，34.83 秒 |
| HTTP smoke | 0.33 秒；health/Web/Reviewer queue=200，未认证 queue=401，Learner queue=403，随机 Review=404 |
| OpenAPI | 58,338 bytes，SHA-256 `e97bdead8c48c33c72f356ac6ffcdf6e4fd5ba55b82c9a79e51232be4cba8e3f`；四个 Reviewer path 与 `FinalizeReviewCommand`/detail/mutation schemas 的 `jq` 断言通过 |
| Playwright | 早期及最终真实 Chromium；最终覆盖真实 Learner 加入/提交、独立 Reviewer 队列/详情/start/四维反馈/REQUEST_REVISION、只读结论和 Learner 修订状态；双会话 console 0 error/0 warning |
| 三视口自动检查 | 390/768/1280 均 `scrollWidth == clientWidth`；截图经视觉复核，无核心动作遮挡或横向溢出 |

显式执行 `security-best-practices` 并完整读取适用 Python/FastAPI、通用 JavaScript、Next.js 与 React 参考后的复核结果：

- role、explicit reviewer、organization 与 object scope 同时存在于查询；同组织其他 Reviewer、跨组织 Review 和 Learner 越权均有负向自动化，不仅依赖随机 UUID；
- 所有写入由共享 session/CSRF middleware 保护，真实 Learner session 的 CSRF 正/负路径已有回归；Next Server Actions 只从 httpOnly session cookie 和 CSRF cookie 转发，不使用 browser local/session storage；fixture identity 仅可在 local/test；
- strict Pydantic 拒绝额外字段、重复/缺失 rubric key、短反馈和不一致决定；SQLAlchemy 参数化查询，无动态 SQL、eval/Function、危险 HTML、shell/subprocess 或用户输入路径拼接；
- Review/Assignment 行锁、expected revision、唯一约束、幂等记录和 DB immutable trigger 共同覆盖并发与历史；GET 零写入由前后计数证明；
- 审计与 outbox 不记录 submission body、rubric feedback、session/invite token 或附件 bytes。最终源码检索未发现新增敏感日志或浏览器凭证存储。

## 5. 浏览器证据

- [早期 Reviewer 开始后工作台](../output/playwright/wp04-early/.playwright-cli/page-2026-07-20T20-28-59-387Z.png)
- [最终只读结构化 Evaluation](../output/playwright/wp04-final/wp04-final-evaluation-history.png)
- [最终 Learner 修订反馈](../output/playwright/wp04-final/wp04-final-learner-revision-feedback.png)
- [最终 390 视口](../output/playwright/wp04-final/wp04-final-review-history-390.png)
- [最终 768 视口](../output/playwright/wp04-final/wp04-final-review-history-768.png)
- [最终 1280 视口](../output/playwright/wp04-final/wp04-final-review-history-1280.png)

浏览器严格沿用 `~/Library/Caches/ms-playwright/chromium-1232`，没有执行 install-browser。skill wrapper 无执行位，全部成功调用均显式使用 `bash`；CLI 通过配置中的 `executablePath` 使用既有 Chrome for Testing binary。最终可核验浏览器窗口从 `2026-07-21 04:33:27 +0800` 到 `04:39:13`，约 5 分 46 秒；这是自动浏览器 smoke，不是真人 UAT。

## 6. 失败、重试与分段耗时

没有为实现/分析伪造总人时；仅记录可核验命令输出与浏览器时间：

| 分段 | 记录 |
| --- | --- |
| bootstrap + pre-change | 6.83 秒；API 7.31 秒；Web 9.61 秒 |
| migration 首轮 | `0007` 的 UPDATE 在 target alias JOIN 中引用目标表，PostgreSQL 拒绝；事务回滚，测试汇总 16 passed/17 failed，20.47 秒。改为 correlated subquery 后旧 33 tests 全通过，14.28 秒 |
| 持久库升级 | migrate 2.04 秒；seed 1.63 秒；升级前后核心计数与 scope mismatch 查询均成功 |
| backend targeted | 加入 WP-04 用例后 38/38，15.37 秒；显式 Learner organization scope 补强后 38/38，15.40 秒 |
| web targeted | 第一条真实 Reviewer 页面接通后 lint/type/build 6.56 秒 |
| browser early | 首次命令把尚未创建的 artifact 目录设为 workdir，进程启动前失败；创建目录后 wrapper 默认寻找系统 Chrome 又失败。没有安装浏览器，改用批准缓存 executable 后完成 queue→detail→start，约 53 秒可核验成功窗口，console 0/0 |
| browser final | 5 分 46 秒；一次 `run-code` overflow 表达式被 CLI parser 拒绝，改用 `eval` 后 1280/768/390 均取得相等宽度；失败表达式不计为通过 |
| final gates | `make verify` 14.30 秒；pip check 1.13 秒；npm audit 1.20 秒；Compose 34.83 秒；HTTP 0.33 秒 |

上述失败均保留为真实迭代事实，没有把部分输出、回滚事务或失败命令计为通过。

## 7. 已知债务、边界与 NOT_RUN

已知本地/后续工作债务：

- Muchen Journey ops doctor 仍不识别此 Greenfield 仓库；本工作包没有修复外部 helper，也没有新建第二套脚本。
- 迁移前已有 Evaluation 不具备维度级结构化反馈；系统保留原始历史并显式标为 V0，不补造内容。未来若要补充只能追加独立事实，不能覆盖。
- 本地 Reviewer 浏览器使用 local/test fixture identity；真实 Reviewer 的身份提供方接入、人员独立性与校准需在受控环境验证。fixture 在 staging/production 为 fail-closed。
- WP-03 的本地附件存储/扫描限制仍成立；Reviewer API 的受控附件下载已有回归，本工作台展示固定附件元数据与可用状态。真实对象存储、签名 URL、扫描服务和物理 ACL 不在本工作包内。
- APPROVE 路径为了旧回归保留最小 `HANDOFF_READY` 写入；完整 Outcome 生命周期、通知投递/重试和跨域历史明确属于 WP-05。

以下门禁明确为 `NOT_RUN`：

- 真人 Learner/Reviewer 标准、修订、重复提交理解与签字 UAT；
- 真实 Reviewer 与 Learner 的组织独立性证明、双人复核、Reviewer 校准/一致性测试；
- staging/production 身份、secret、cookie/TLS、网络策略、真实对象存储/扫描和物理 PostgreSQL/object ACL 审计；
- 备份恢复、Evaluation/附件恢复、生产迁移/rollback 与灾难恢复演练；
- release candidate 冻结、镜像/SBOM 发布审查、双人发布批准、G4/G5 发布签署和生产观察；
- WP-05 完整 Outcome/通知 outbox worker/跨域时间线，以及 WP-06 运营、导入和生产运行。

仓库仍是无 HEAD、全部 untracked 的原始工作树形态；本工作包没有 stage、commit、push、分支或部署。

结论：`WP-04 LOCAL BUILD VERIFIED`。这不是 `UAT PASSED`、`RELEASE GO` 或 `PRODUCTION READY`。
