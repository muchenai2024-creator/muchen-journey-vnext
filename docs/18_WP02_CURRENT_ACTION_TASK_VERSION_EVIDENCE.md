# 18｜WP-02 Current Action 与任务版本构建证据

状态：`AS_BUILT`  
版本：V0.1  
日期：2026-07-21  
验证环境：本地 Docker Compose，未发布  
Owner：Liu Mowen（初始 Product + Tech Owner）

## 1. 逐项审计结论

本工作包没有把 walking skeleton 已有路径当作完成。开工审计先按 03/04/05/07/08/09/10/13/15 逐项对照，发现并关闭以下缺口：

| 批准要求 | 开工时事实 | WP-02 As-Built | 自动化/合同证据 |
| --- | --- | --- | --- |
| `REQ-BR-003` 唯一权威 Current Action | 仅按一个 Assignment status 映射；无 Enrollment、无任务/多任务优先级 | Resolver 覆盖无 Enrollment、待确认/取消、无任务、修订优先、可执行、等待、完成与下一任务；只返回一个 action | `tests/test_domain.py` 全矩阵；`GET /api/v1/me/current-action` |
| TaskDefinition 稳定身份 | `stable_key` 直接放在 TaskVersion | 独立 TaskDefinition，组织内 stable key 唯一；`created_by` 是指定 content owner，只有 owner 可发布 | `0003_current_action_tasks`；TaskDefinition create/list/publish 权限用例 |
| Published TaskVersion 完整且不可变 | 仅 title/purpose/instructions/criteria/rubric；无 owner/review/source/SLA 等完整合同 | 版本包含 15 号文档全部内容、Rubric、来源、变更、校准、敏感级别、audience、发布/复核责任与时间；数据库 trigger 拒绝 UPDATE/DELETE | publish schema 正负向、DB update/delete 失败测试、OpenAPI |
| Assignment 固定任务版本 | Assignment 只引用 TaskVersion，无稳定定义与顺序 | Assignment 同时固定 Definition + Version，Enrollment 内任务和 position 唯一；发布 V2 不移动在途 V1 | `AT-CONTENT-005` 自动化；复合 FK/唯一约束 |
| 服务端 allowed commands 权威 | task page 自己按 status 组合按钮 | Current Action 和 Assignment detail 都从领域规则返回 commands；Learner 页面只按 commands 渲染动作 | Domain/API 测试；Web source + browser smoke |
| Learner 5 秒理解合同 | 首页显示内部 enum，责任人/SLA 硬编码；任务页硬编码 TSK/version | 首页显示阶段、目标、原因、反馈责任人与时限、唯一 CTA；任务页显示真实 stable key/version、目标、标准、交付、工作区和次级 Rubric 披露 | 两次 Playwright `/app → task` smoke；截图见第 5 节 |
| 权限与对象 scope | skeleton 有 Learner owner check，无 Task publish 权限 | Learner/Reviewer 不能访问 Task config；publish 要求同组织 Operator content owner + 同组织 ACTIVE Reviewer；Learner Assignment 按 actor/org/Enrollment owner 查询，越权返回 404 | 角色、跨组织、IDOR、非法 reviewer 负向测试 |
| 空库与 WP-01 持久库升级 | 只有 0001/0002 | 0003 建模/约束/不可变 trigger，0004 修复旧 skeleton Rubric，0005 补齐发布证据；seed 增量幂等 | 空库 base↔head；WP-01 开发库 0002→0005，原 2 Assignment/4 Invite 保留 |
| 合同与追溯 | OpenAPI/13 号文档仍只描述 skeleton | OpenAPI 新增 TaskDefinition publish、完整 TaskVersion、CurrentAction/Assignment 响应；13 号文档回写 WP-02 与 WP-03 边界 | `contracts/openapi.json` 可由当前 app 重生且 `jq` 校验通过 |

## 2. 实际实现

- 新增 TaskDefinition DRAFT/PUBLISHED/WITHDRAWN 状态、组织/owner/revision 约束，以及受控 create/list/publish API；没有通用 PATCH、SQL UI 或任意 status editor。
- TaskVersion 发布按 Definition 行锁串行生成单调版本，要求 expected revision、幂等 key、同组织有效 Reviewer；发布同时写最小 AuditEntry 和 `task_version.published.v1` outbox。
- TaskVersion 发布合同拒绝额外字段、缺失 Rubric 维度、非法 Reviewer，以及本工作包不批准的附件类型/大小；附件字段在 WP-02 只能是 `[]`/`0`。
- 数据库级不可变 trigger 同时阻止 Published TaskVersion UPDATE 和 DELETE；新版本是唯一内容修改路径。
- Assignment 增加 task_definition_id、position、assigned_at 和复合 FK；在途 Assignment 永久引用被分配时的 TaskVersion。
- Current Action Resolver 将 Enrollment 与全部 Assignment 组合，业务优先级为 NEEDS_REVISION → AVAILABLE/IN_PROGRESS → SUBMITTED/IN_REVIEW → 最后完成结果；CANCELLED 不生成写动作。
- Learner `/app` 首屏不再暴露内部 action enum；任务页不再硬编码 `TSK-001/V1`，也不再从 status 推导动作。
- 为保留 WP-01/骨架回归，0004 把上一持久库简化 Rubric 原子迁移到批准的四维合同；Reviewer 页面最小适配 `dimension_key`，未扩展 WP-04 工作台。

## 3. 迁移证明

### 空库

最终 `make verify` 先执行 `0005 → base`，再执行 `base → 0001 → 0002 → 0003 → 0004 → 0005`、seed 与全套测试，结果 `30 passed in 0.78s`。这同时验证所有 WP-02 downgrade/upgrade 能顺序运行。

### 上一工作包持久库

升级前只读快照：Alembic head=`0002_invites_identity_sessions`，Organization=1、TaskVersion=1、Assignment=2、Invite=4。升级后：

- Alembic head=`0005_task_publish_evidence`；
- TaskDefinition=1、TaskVersion=1、Assignment=2、Invite=4；
- 两个 Assignment 都通过 Definition/Version 复合关系继续引用 `TSK-001 V1`，position=1；
- 旧 Rubric 已具有 `dimension_key/purpose/evidence_expected/levels/feedback_prompt/blocking_rule`；
- 来源、change summary 与校准说明已补齐，校准文本明确写明真人门禁 `NOT_RUN`。

首个 0002→0003 尝试因 Alembic revision id 超过 32 字符而事务回滚（1.67 秒）；缩短 id 后原命令重试通过（1.12 秒），没有部分迁移。该失败与修复保留为真实 migration evidence。

## 4. 机器门禁

| 门禁 | 最终结果 |
| --- | --- |
| `make bootstrap` | 通过，25.42 秒；API/Worker images 构建，Web `npm ci`，0 vulnerabilities |
| 变更前回归 | `19 passed in 0.86s`，命令 7.77 秒，作为 WP-01/骨架基线 |
| 最终定向 `make api-test` | `30 passed in 0.77s`，命令 6.76 秒；含 Domain、DB、API、权限、迁移、幂等和版本固定 |
| `make web-check` | ESLint、TypeScript、Next 16.2.10 production build 通过；最终定向命令 5.32 秒 |
| `make verify` | `30 passed in 0.78s`；Web lint/type/build；`isolation checks passed`；总计 10.67 秒 |
| `npm audit --audit-level=moderate` | `found 0 vulnerabilities`，1.69 秒 |
| `docker compose up -d --build --wait` | 最终构建并达到 Compose ready；API/DB/DB-test 显式 healthy，Web/Worker running（两者未配置 healthcheck），46.43 秒 |
| OpenAPI | 37,558 bytes；TaskDefinition/PublishTaskVersion/CurrentAction/Assignment schemas 存在；`jq` 解析与关键路径断言通过 |
| HTTP smoke | health/current action/assignment/task definitions/Web `/app` = 200；未认证 current action=401；Learner ops=403；随机 Assignment IDOR=404 |
| Playwright | `/app → /app/tasks/{id} → 展开“评审会看什么”` 通过；页面显示 WP-02、唯一 CTA、真实任务版本/标准/交付/Rubric；0 error、0 warning |

安全实现复核未发现 `dangerouslySetInnerHTML`、动态 SQL 拼接、token browser storage、eval/exec 或前端信任隐藏权限等新增风险。发布输入由严格 Pydantic schema、参数化查询、org/owner/role/status/revision/idempotency 检查与 DB 约束共同防护。

## 5. 浏览器证据

- 早期真实路径：[WP-02 early task page](../output/playwright/wp02-early-task-page.png)
- 最终任务理解与 Rubric：[WP-02 final task understanding](../output/playwright/wp02-final-task-understanding.png)

浏览器环境事实：首次 `open` 因 Playwright 默认 Chrome distribution 不存在而失败；`install-browser chrome` 因本机 sudo 不可用而失败；随后 `chromium-1232` 安装产物在 `2026-07-20 23:57:46 +0800` 写入 `INSTALLATION_COMPLETE`。安装命令完成后滞留，收到明确指示后终止，没有再次下载；最终使用 `open --browser chromium` 成功。

## 6. 耗时分段

可复核执行窗口从审计计时锚点 `2026-07-20 23:27:32 +0800` 到最终浏览器截图 `2026-07-21 00:23:41 +0800`，共 56 分 09 秒；此前技能/文档阅读与 bootstrap 不计入该窗口。

| 分段 | 记录 |
| --- | --- |
| implementation / requirement audit | 审计锚点到最后产品/测试代码修改 51 分 12 秒；按 V0.2 要求期间穿插短反馈，故不是可与 targeted 简单相加的纯键入时间 |
| targeted | 有 `/usr/bin/time` 的 API/Web 定向命令合计 100.81 秒；真实失败为 migration id 1 次、IDOR fixture 插入顺序 1 次；另有一次误用不存在的 `make web-test`（0.00 秒），均修正后重跑通过 |
| browser | 两轮成功 smoke 的 Playwright 活跃命令约 58.6 秒；早期路径在第一条页面接通后执行，最终路径在容器重建后执行 |
| full gate | `make verify` 10.67 秒 + npm audit 1.69 秒 + 最终 Compose build/wait 46.43 秒 + HTTP smoke 0.30 秒，共 59.09 秒；final browser 单列，不重复计入 |
| external/tool wait | Chromium 下载开始时间未被独立 stopwatch 捕获，记为 `NOT_MEASURED_EXACTLY`；可核验安装完成 marker 为 23:57:46，marker 到成功打开浏览器为 6 分 48 秒，包含滞留命令终止与 launcher 选择，不包含产品代码执行 |
| evidence | OpenAPI、追溯和本 As-Built 在最终门禁后完成；未为了文档重复运行无代码变化的完整门禁 |

## 7. 工具债务

显式使用的 `muchen-journey-ops` helper 对本 Greenfield 仓库执行 `doctor` 返回 `Not a compatible Muchen Journey repository`。按技能和 10 号文档边界，没有新建第二套命令或修改仓库适配 helper；继续使用现有 `make api-test/web-check/verify`、Compose、curl 和 Playwright，并把 helper 不兼容记录为工具债务。

React/Next 实现按 `vercel-react-best-practices` 复核：独立异步读取使用 `Promise.all`，数据只在 server component/server action 获取，未增加 client-side fetching/state machine，动态路径编码，生产 build 通过。权限、输入和不可变边界按 `security-best-practices` 复核并增加负向测试。

## 8. 明确边界与未运行门禁

本工作包没有实现或扩大：

- WP-03 附件、对象存储、病毒扫描、完整提交/修订与草稿恢复；
- WP-04 Reviewer 队列/材料/并发 finalize 扩展；
- WP-05 通知投递历史、Outcome 历史和时间线；
- WP-06 完整运营 UI、Enrollment 处理、审计查询、离线导入与生产运行；
- 生产部署、生产迁移、旧业务数据导入、stage/prod 物理资源或发布操作。

以下门禁保持 `NOT_RUN`，本地 fixture/浏览器 smoke 不能替代：

- `AT-UX-001/002` 的真实新人 5 秒当前行动理解测试及目标 ≥90%；
- 真实 Reviewer 内容校准、UAT preview、Product/QA 签署；
- 390/768/1280 三视口、纯键盘和真实辅助技术人工验收；
- staging/production 真实 Operator/Reviewer 身份、物理 DB role/ACL、secret store、TLS/cookie、告警；
- 备份恢复、回滚、发布候选、生产观察窗口和 G4/G5 签字。

结论：`WP-02 LOCAL BUILD VERIFIED`。这不是 `UAT PASSED`、`RELEASE GO` 或 `PRODUCTION READY`。
