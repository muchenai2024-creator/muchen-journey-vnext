# 19｜WP-03 提交、附件与修订构建证据

状态：`AS_BUILT`  
版本：V0.1  
日期：2026-07-21  
验证环境：本地 Docker Compose，未发布  
Owner：Liu Mowen（初始 Product + Tech Owner）

## 1. 开工 Gap Audit

本工作包先完整读取 README、00、03、04、05、06、07、08、09 V0.2、10 V0.2、12、13、14、15、16、17、18，并按批准合同重新审计 walking skeleton。结论是原有文本提交/修订路径只能作为回归基线，不能关闭 WP-03：

| 批准要求 | 开工时事实 | WP-03 As-Built | 主要证据 |
| --- | --- | --- | --- |
| `REQ-BR-004` 首次提交 | `SubmissionVersion` 直接挂 Assignment，没有稳定 Submission 容器；walking skeleton 只返回通用 command | 新增一个 Assignment 一个 Submission 容器；首次提交只追加 Version 1，原子创建固定 Review、更新 Assignment、删除服务端草稿并写最小审计/outbox | `0006_submission_attachments`；`submission_routes.py`；API/浏览器用例 |
| `REQ-BR-006` 修订闭环 | 领域状态可以再次调用文本 submit，但没有历史查询、草稿恢复和 DB 不可变保护 | NEEDS_REVISION 只通过服务端 `allowed_commands=[submit_revision]` 进入同一命令；追加 Version 2 和新 Review，Version 1 正文、附件关联、Evaluation/反馈引用不覆盖 | revision API/DB test；最终 Playwright revision history |
| 不可变 SubmissionVersion | 只有唯一 `(assignment_id, version_no)`，应用代码仍可 UPDATE/DELETE | SubmissionVersion 唯一 `(submission_id, version_no)`；DB trigger 拒绝 UPDATE/DELETE；版本附件关联和已绑定 Attachment 也拒绝 UPDATE/DELETE | `AT-DATA-005` DB 负向测试 |
| Attachment 合同与隔离 | TaskVersion 附件策略固定为空，未实现上传、存储、扫描或下载 | V2 固定 TXT/PDF/PNG/JPEG、5 MiB；受控上传意图、原始 bytes PUT、complete、删除、再授权下载；org/owner/assignment/purpose + 复合 FK 双层隔离 | 文件/权限/跨对象/恶意样本/API/OpenAPI 测试 |
| 幂等、并发、expected revision | walking skeleton 覆盖基本 idempotency，但没有完整提交结果、草稿、附件或并发版本事实 | presign/complete/draft/submit 记录 canonical request hash；同 key 同请求 replay，同 key 异请求 409；Assignment 行锁 + expected revision；同 key 并发只建一版，不同 key 并发一成功一冲突 | ThreadPool API test；双标签浏览器冲突 |
| 草稿与重试恢复 | 只有浏览器 textarea，没有服务端 draft | SubmissionDraft 绑定 org/owner/assignment，正文与 READY 附件选择可保存；刷新恢复；成功提交删除；409 在页面局部呈现且不清空当前输入 | API draft replay/refresh；Playwright refresh + conflict |
| Learner 真实路径 | 任务页只完成 WP-02 理解/开始/文本骨架 | 任务页只消费服务端 commands；支持局部上传错误、READY 选择、草稿、首次提交、修订反馈、只读历史与新版本追加 | Next production build；早期及最终 Playwright |
| 迁移与既有数据 | 开发库 head=0005，4 Invite、2 Assignment、1 TaskVersion | 0006 可由空库构建；0005 开发库升级到 0006 后原 4 Invite、2 Assignment、TSK-001 V1 全部保留，并增量加入 V2；原两个 Assignment 继续固定 V1 | 持久库升级前后只读计数；最终 `make verify` base↔head |

## 2. 实际实现合同

### 2.1 Submission 与版本历史

- `Submission` 是 Assignment 的唯一容器，`current_version_no` 单调增加；`SubmissionVersion` 只追加，不提供 PATCH/DELETE API。
- 首次提交与修订共用 `POST /api/v1/me/assignments/{id}/submissions`，但合法动作完全来自服务端状态与 `allowed_commands`；前端不维护第二套状态机。
- 每个新版本固定一个新的 Review；旧 Review/Evaluation/反馈继续引用旧 SubmissionVersion。修订不会移动旧评审引用。
- `GET /api/v1/me/submissions/{id}` 和 Assignment detail 返回按版本升序的正文、附件元数据、Review 状态、结论与反馈；查询按 Learner + organization + Enrollment owner 裁剪。
- 数据库 trigger 阻止历史 SubmissionVersion、版本附件关联以及已绑定附件被 UPDATE/DELETE；自动化直接执行 SQL 并确认失败。

### 2.2 Attachment

- 上传意图固定绑定 `organization_id`、`owner_id`、`assignment_id` 和 `purpose=SUBMISSION_EVIDENCE`；storage key 只由服务端 UUID/scope 生成，不使用用户文件名作为路径。
- 文件名先做 NFKC 规范化，拒绝空名、隐藏名、路径分隔符、控制字符与扩展名/内容类型不匹配；数据库不保存客户端路径。
- 全局和 TaskVersion 均限制单文件不超过 5 MiB；允许类型为 UTF-8 TXT、PDF、PNG、JPEG；上传时流式累计并同时校验 Content-Length、实际长度、SHA-256 和最小 magic/content 特征。
- 本地验证使用 `/tmp/journey-next-attachments` 下的 vNext 自有存储抽象、边界检查与原子替换。确定性门禁拒绝 EICAR marker，并明确记录为 `LOCAL_CLEAN/LOCAL_REJECTED`。
- 该门禁只用于本地可复现测试，**不是**真实病毒扫描；本地路径也不是批准的生产对象存储。真实扫描、S3-compatible storage、短时对象 URL 和物理 ACL 保持 `NOT_RUN`。
- READY 附件只有 owner 可绑定；绑定时再次锁行并复核 org/owner/assignment/purpose/type/size/未绑定。关联表同时携带 org/assignment，复合外键在 DB 层拒绝跨 Assignment 关联。
- Learner 仅能下载自己的 READY 附件；Reviewer 只有在其被明确分配的 Review 固定引用该 SubmissionVersion 时才能下载。其他 owner/object/org 均返回 404。

### 2.3 草稿、重试与并发

- `PUT /api/v1/me/assignments/{id}/draft` 保存正文及 READY 附件引用，要求 expected revision 和 Idempotency-Key；同 key replay 返回首次 draft revision。
- 提交成功后服务端草稿原子删除；失败时客户端受控 textarea 不因 server action 错误重置。
- 提交使用 actor/command/key/request hash；同 key 同请求返回同一 SubmissionVersion 并标记 replay，同 key 不同 body/附件返回 `IDEMPOTENCY_KEY_REUSED`。
- Assignment 行锁串行化并发提交。自动化证明同 key 并发响应 200/200 且只有一个版本，不同 key 并发响应 200/409 且只有一个版本。
- 最终 Playwright 用两个共享会话标签页提交相同 revision：先提交标签成功，后提交标签显示 `VERSION_CONFLICT` 的可恢复信息和 request ID，并保留另一段未提交正文。

### 2.4 Web 与范围边界

- Next server component 读取 Assignment/Submission/Draft；client component 只管理尚未提交的 textarea/checkbox 和 action pending/error，不读取浏览器 token storage、不推导业务状态。
- 上传错误局部显示，提示正文与服务端草稿不受影响；合法文件显示 READY 后才能被选择；保存草稿、提交与修订有独立稳定 idempotency key。
- 任务页展示最新修订反馈、旧版本正文/附件名称/该版反馈，并明确旧历史只读。
- 为保留 walking skeleton 回归，现有 Review start/finalize 仅做 Submission 容器适配；没有扩展 WP-04 队列、评审工作台或 finalize 产品范围。

## 3. 迁移与数据证明

### 3.1 空库 base↔head

最终 `make verify` 对测试库先执行 `0006 → base`，再执行 `base → 0001 → … → 0006`、增量 seed 和全部测试。结果为 `33 passed in 1.39s`，证明空库全迁移链、downgrade 顺序和最新模型可执行。

### 3.2 WP-02 持久开发库升级

升级前只读事实：Alembic head=`0005_task_publish_evidence`，Organization=1、Invite=4、Assignment=2、TaskDefinition=1、TaskVersion=1、SubmissionVersion=0；两个 Assignment 都是 AVAILABLE 并固定 `TSK-001 V1`。

执行 `alembic upgrade head && python -m journey_api.seed` 后（2.37 秒）：

- head=`0006_submission_attachments`；
- Organization=1、Invite=4、Assignment=2、TaskDefinition=1；
- TaskVersion 从 1 增至 2，V2 承载附件 allowlist/5 MiB；
- 两个既有 Assignment 仍固定 AVAILABLE + V1；
- Submission/SubmissionVersion/Attachment 初始均为 0，没有为旧对象伪造业务事实。

复合 scope 外键补强后，为让已经执行过 0006 的本地库与最终 0006 定义一致，又执行一次显式 `0006 → 0005 → 0006`（3.23 秒）。该次执行前后的 Organization/Invite/Assignment/TaskVersion/SubmissionVersion 分别保持 1/6/3/2/2；两个原 WP-02 Assignment 仍固定 V1。由于 downgrade 到 WP-02 schema 必然移除 WP-03 附件表，1 条早期浏览器 Attachment 元数据不保留；这是本地 schema 回退事实，不是生产数据回滚证明。备份恢复/生产回滚保持 `NOT_RUN`。

## 4. 自动化、安全与合同门禁

| 门禁 | 最终结果 |
| --- | --- |
| `make bootstrap` | 通过，6.36 秒；容器依赖可构建，Web `npm ci`，0 vulnerabilities |
| 变更前 API 基线 | `30 passed in 1.02s`，命令 7.49 秒 |
| 变更前 Web 基线 | ESLint/TypeScript/Next production build 通过，11.94 秒 |
| 最终定向 `make api-test` | `33 passed in 1.41s`，命令 16.29 秒；含 migration、文件合同、scope、DB 不可变、修订、draft、幂等与并发 |
| 最终定向 `make web-check` | ESLint、TypeScript、Next 16.2.10 production build 通过，7.08 秒 |
| 最终 `make verify` | `33 passed in 1.39s`；Web lint/type/build；`isolation checks passed`；总计 28.21 秒 |
| Python installed dependency consistency | `python -m pip check`：`No broken requirements found`，1.51 秒 |
| `npm audit --audit-level=moderate` | `found 0 vulnerabilities`，1.15 秒 |
| 最终 Compose | `docker compose up -d --build --wait` 构建候选镜像；随后显式 `up -d --wait` 1.70 秒确认 API/DB/DB-test healthy，Web/Worker running |
| OpenAPI | 51,997 bytes，SHA-256 `730c976bc2277f6db6fe33fd5456fb9176b61e84d06162f837179e4a8b771e55`；关键 path/schema、binary request body、413 与 octet-stream 响应 `jq` 断言通过 |
| HTTP smoke | 0.25 秒；health=200、Web=200/WP-03 footer、fixture Learner current action=200、未认证 current action=401、Learner ops=403、Operator attachment=403、随机 submission history=404 |
| Playwright | 早期与最终两轮真实 Chromium；最终覆盖键盘加入、附件局部失败/成功、draft refresh、双标签 409、首次提交、revision history、Version 2；console 0 error/0 warning |
| 三视口自动检查 | 390/768/1280 均 `scrollWidth == clientWidth`；截图经视觉复核，无核心动作遮挡或横向溢出 |

显式执行 `security-best-practices` 复核及适用的 Python/FastAPI、通用 JavaScript、Next.js、React 参考：

- 没有发现 `dangerouslySetInnerHTML`、动态 eval/Function、shell/subprocess、browser local/session storage 凭证、动态 SQL 拼接或新增敏感正文/token 日志；
- Pydantic strict schemas、参数化 SQLAlchemy、CSRF/session middleware、role/org/owner/object scope、expected revision、idempotency、DB FK/unique/check/trigger 共同承担输入与授权边界；
- 审计只记录资源引用、类型/大小/数量和 request ID，不复制 submission body、文件 bytes 或 invite/session token；
- 本地恶意 marker 测试和内容类型测试通过，但不声明真实 AV 能力。

## 5. 浏览器证据

- [早期草稿刷新与附件恢复](../output/playwright/wp03-early-draft-restored.png)
- [早期修订反馈与 Version 1 历史](../output/playwright/wp03-early-revision-history.png)
- [最终 390 视口](../output/playwright/wp03-final-task-390.png)
- [最终 768 视口](../output/playwright/wp03-final-task-768.png)
- [最终 1280 视口](../output/playwright/wp03-final-task-1280.png)
- [最终双标签冲突保留正文](../output/playwright/wp03-final-conflict-preserved.png)
- [最终修订草稿恢复与 Version 1 只读历史](../output/playwright/wp03-final-revision-history.png)

浏览器使用现有 `~/Library/Caches/ms-playwright/chromium-1232/INSTALLATION_COMPLETE`，没有重复执行 install-browser。skill wrapper 文件本身不可执行，首次直接调用以 exit 126 失败；之后显式用 `bash playwright_cli.sh` 调用同一 wrapper 和已安装 Chromium，未 chmod、未下载第二份运行时。

最终浏览器候选的可核验活动窗口从 `2026-07-21 03:50:09 +0800` 打开 Chromium 到 `03:56` 完成 console 检查并关闭，约 6 分钟；早期 draft/revision 里程碑窗口从 `03:35:26` 到 `03:40:51`，5 分 25 秒。两者均为自动浏览器 smoke，不是人类 UAT。

## 6. 失败、重试与分段耗时

实现/文档审计没有独立可靠 stopwatch，因此不编造总人时；机器命令和浏览器里程碑按实际输出记录：

| 分段 | 记录 |
| --- | --- |
| bootstrap + pre-change | bootstrap 6.36 秒；API 7.49 秒；Web 11.94 秒 |
| backend targeted iteration | 首轮 29/30（14.67 秒）：walking skeleton 断言仍取旧 `status`，改为 `assignment_status`；次轮 32/33（13.99 秒）：strict draft response 未声明 replay 字段，补 schema；随后 33/33（15.97 秒） |
| web targeted iteration | 首条页面接通后 5.88 秒通过；局部附件恢复组件后最终 7.08 秒通过 |
| migration strengthening | 复合 scope 外键后 33/33（16.29 秒）；持久库 0006 重建 3.23 秒；末尾一次只读展示查询误把 stable key 当 TaskVersion 列而失败，修正 join 后确认 V1/V2 与原两个 V1 Assignment |
| browser early | 5 分 25 秒可核验路径窗口；Reviewer fixture 定位先后误用不存在的 DB role 和 `reviews.created_at`，两次均只读查询失败、HTTP 404、无状态迁移；第三次正确后完成 revision |
| browser final | 约 6 分钟；首次新 invite 使用了错误的手写 Reviewer UUID，API 422 且未创建业务对象；读取 fixture 常量后重试成功 |
| final gates | `make verify` 28.21 秒；pip check 1.51 秒；npm audit 1.15 秒；HTTP 0.25 秒；Compose 最终显式 wait 1.70 秒 |
| Compose retry | build/wait 后第一次立即 `ps` 快照落在 API/Web recreate 窗口，只看见 DB/worker，未计为通过；日志确认服务启动后重新执行 `up -d --wait` 并取得健康结果 |

上述失败均保留为真实迭代事实；没有把失败命令或部分输出计为通过。

## 7. 技能与工具债务

- `muchen-journey-ops:operate-muchen-journey` 的 doctor 对本 Greenfield 仓库返回 `Not a compatible Muchen Journey repository`。按技能要求没有创建第二套脚本，继续使用仓库既有 Make targets、Compose、curl 和 Playwright；这是未解决的 helper 兼容债务。
- React/Next 变更按 `vercel-react-best-practices`：server component/server action 负责数据与命令，client state 只保存临时表单，pending/error 局部化，没有 client fetch waterfall 或客户端工作流状态机。
- 浏览器按 `playwright` skill 使用现有 Chromium；权限位问题如实记录，未重复安装。
- 安全复核按 `security-best-practices` 及适用语言/框架参考执行；本地 scope/输入/文件负向测试已自动化，外部和物理控制未伪造。

## 8. 已知债务、边界与 NOT_RUN

已知本地/后续工作债务：

- 本地附件存储和确定性 marker 门禁只用于合同验证；真实对象生命周期、扫描回调、隔离桶、物理 ACL、过期清理和孤儿对象回收尚未实现。
- 0006 downgrade 是开发/测试 schema 回退，不是附件数据可逆的生产 rollback；附件备份恢复与 release rollback 需要独立演练。
- Reviewer API 已能按固定 Review 下载被引用附件，但 Reviewer 材料 UI、队列/finalize 扩展属于 WP-04，未越界实现。
- Attachment 一年保留、Submission 三年保留与幂等记录 30 天的自动清理/法定保留运行作业属于后续运营工作包，当前没有运行。

以下门禁明确为 `NOT_RUN`：

- 真人 Learner/Reviewer 标准路径、修订路径、重复点击理解与签字 UAT；
- 真实病毒扫描服务、真实 S3-compatible 对象存储、短时签名 URL、独立 bucket/key、恶意文件沙箱；
- staging/production 配置、身份、secret、TLS/cookie、网络策略、容器镜像扫描与 SBOM 发布审查；
- PostgreSQL/object storage 物理 role/ACL 和跨资源网络隔离审计；
- 备份恢复、附件恢复、生产迁移/rollback、灾难恢复演练；
- 发布候选冻结、双人发布批准、G4/G5 发布签署、试点指标和生产观察；
- WP-04 Reviewer 队列/finalize 扩展、WP-05 通知/Outcome 历史、WP-06 运营/导入/生产运行。

仓库仍是无 HEAD、全部 untracked 的原始工作树形态；本工作包没有 stage、commit、push、分支或部署。

结论：`WP-03 LOCAL BUILD VERIFIED`。这不是 `UAT PASSED`、`RELEASE GO` 或 `PRODUCTION READY`。
