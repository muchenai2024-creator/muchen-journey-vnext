# 10｜交付计划与工程规则

状态：`APPROVED_FOR_BUILD`  
版本：V0.3
日期：2026-07-21
文档 Owner：Tech Lead + Product Owner  
目标：以一个稳定候选完成一个真实闭环；控制 WIP 和共享改动，避免通过大量并行分支制造集成债务。  
变更说明：根据 WP-01 的 39 分 32 秒实测增加执行节奏、耗时口径与技能选择规则；根据 WP-01～WP-07 横向复盘增加六项 P0 开工硬规则，并记录 `muchen-journey-ops` V0.3 兼容闭环。

## 1. 交付原则

1. 开发始于批准的需求和验收，不始于页面或脚手架；
2. 先交付端到端 walking skeleton，再扩充每一层；
3. 一个工作包包含需求、代码、迁移、合同、测试和运行影响；
4. 共享合同由一个 Owner 串行修改；
5. 同一时间只有一个可发布候选；
6. 小分支、短反馈、稳定观察，不追求提交数量；
7. 任何紧急修复都不能越过 Greenfield 隔离红线；
8. 新抽象必须由两个已稳定的真实用例证明，不为未来空间预建框架。

## 2. 阶段与门禁

| 阶段 | 目标 | 主要交付物 | 退出条件 |
| --- | --- | --- | --- |
| G0 文档冻结 | 关闭会改变方向的决定 | 00–15 号文档、原型、签署 | 所有构建方向已批准；正式 Build GO |
| G1 独立基座 | 从空环境构建独立系统 | 新 repo、CI、空库 0001、Web/API/Worker、observability | `AT-ISO-001/002/003/005` 通过 |
| G2 Walking Skeleton | 一名 fixture 新人完成最小闭环 | 身份→任务→提交→评审→结果 | 真实 DB、无 mock fallback；标准路径自动化通过 |
| G3 P0 完整业务 | 完成邀请、修订、附件、运营、通知 | `REQ-BR-001..010` | 主线门禁全绿；数据不变量通过 |
| G4 候选与 UAT | 冻结精确候选并验证真实角色 | RC、导入/恢复/回滚演练、UAT | Sev-1/2=0；真实标准/修订路径签字 |
| G5 独立试点 | 在 vNext 环境小范围运行 | 试点、观察、支持和复盘 | 指标/护栏满足 `DEC-010`；缺陷趋势收敛 |
| G6 正式切换 | 将目标用户切到 vNext | 切换记录、生产观察、As-Built | Go 签字；旧系统保持只读归档 |

任何阶段失败回到前一门禁，不通过在当前候选上连续叠加临时修复来假装推进。

## 3. 工作包

### WP-00｜仓库与独立基础设施

- 新仓库、保护分支、CODEOWNERS/责任人；
- dev/test/staging/prod 资源命名；
- Web/API/Worker 最小启动；
- PostgreSQL `0001_initial`；
- 独立 secret、日志、trace、release revision；
- 旧依赖/凭证/网络阻断测试。

完成：空 runner + 空 DB 可重复构建/部署；旧仓库和旧系统不存在仍通过。

### WP-01｜邀请、身份与 Enrollment

覆盖 `REQ-BR-001/002`、Invite/Identity/Enrollment 状态、session 安全、运营创建/撤销邀请。

完成：有效/无效/并发邀请与旧凭证拒绝自动化通过。

### WP-02｜Current Action 与任务版本

覆盖 `REQ-BR-003`、TaskDefinition/TaskVersion/Assignment、Current Action Resolver、Learner 当前行动页。

完成：服务端 allowed commands 唯一；前端无本地状态机。

### WP-03｜提交、附件与修订

覆盖 `REQ-BR-004/006`、SubmissionVersion、附件隔离、幂等/冲突/草稿恢复。

完成：首次提交和修订路径自动化；旧版本不可变。

### WP-04｜Reviewer 工作台与结论

覆盖 `REQ-BR-005`、Review/Evaluation、scope、队列、start/finalize、材料完整性。

完成：并发 finalize、越权、缺项和 GET 无副作用通过。

### WP-05｜结果、交接、通知与历史

覆盖 `REQ-BR-007/009/010`、Outcome、outbox、worker、通知和时间线。

完成：通知/AI 故障不污染结果；下一步只产生一次。

### WP-06｜运营、导入与运行

覆盖 `REQ-BR-008`、版本化配置、离线导入、审计、备份恢复、告警和发布。

完成：没有通用 status editor；导入可重放；运行演练通过。

工作包按端到端价值拆分，不允许同时建立多个“空模块框架”再等待集成。

### 单工作包执行节奏

单一 WIP 指同一时刻只推进一个业务工作包，不表示只能改一个文件或一个技术层。一个工作包应按同一条垂直路径依次完成 migration/domain/API/Web/test/evidence：

1. **Preflight**：确认 REQ/AT、非范围、现有脏改动、适用 skill、上一工作包数据库状态和依赖缓存；
2. **最小后端路径**：先建立数据不变量和单条 API happy path，再补权限、失败、幂等和并发矩阵；
3. **最小真实界面**：接通首条用户路径后立即用浏览器验证 hydration/cookie/redirect/focus，不等完整文档和全门禁结束；
4. **收敛验证**：修复定向检查发现的问题，再执行一次完整门禁、容器 smoke 和依赖审计；
5. **证据收尾**：最后生成 OpenAPI/As-Built/追溯更新，明确代码完成、真人 UAT、物理环境和发布状态。

完整门禁不是每个小修改后的反馈工具；开发中优先定向测试，行为稳定后再跑全量。新增 migration、seed 或 fixture 时，空库路径和上一工作包持久库升级路径都属于定向检查，不能推迟到最终浏览器 smoke。

#### WP-01～WP-07 P0 复盘回写

以下六项是后续工作包的开工硬规则，不是可在收尾阶段补写的建议；任一项不满足时，不开始编码或外部环境写入：

1. **逐工作包 Git/PR**：从最新受保护 `main` 的精确 SHA 建立唯一短生命周期 `codex/wp-*` 分支；需求、实现、迁移、合同、测试和静态证据在同一工作包 PR 中闭环。禁止把多个未提交工作包压入后续“初始基线”，禁止直接写受保护 `main`；开工记录 base SHA、分支、Owner、Reviewer 和预期 required check。
2. **统一浏览器预检**：真实浏览器验证前先运行仓库唯一的 `browser-preflight/browser-smoke` 入口；它必须创建证据目录、解析固定 Chromium/config、验证服务与 cookie/redirect 前置条件，并覆盖桌面/平板/手机、console error、横向 overflow、focus/键盘。不得在每个工作包临时重装浏览器、拼接 wrapper 或依赖未记录的本机状态。
3. **迁移与 fixture 先行门禁**：新增 migration/seed/fixture 时，先静态检查 revision 长度、唯一 head、FK/unique/nullable、升降级和命名，再运行空库与上一工作包持久库升级/回退。测试数据统一经过 fixture builder，并生成不含 PII 的表/字段/稳定引用 manifest；禁止在测试中散落手写 UUID、错误表名/字段、隐式 flush 顺序或 SQL alias 假设。
4. **停止态自举与工具 fail-closed**：快速层、主线层和定向门禁必须能从服务全部停止、空缓存/空数据库的声明状态自举，不依赖预启动 API、宿主已有 `rg` 或某个 Python 小版本。必需工具先显式检查；缺失、扫描器错误和未知状态必须失败，优先在固定摘要容器中运行。
5. **Ops Greenfield 兼容**：每个工作包开工和收尾分别运行 `muchen-journey-ops` V0.3+ 的 `doctor` 与适用的 `status/gates`；必须识别 `greenfield-vnext`，并诚实保留候选不一致、`NOT_RUN` 和 `NO_GO`。不得复制旧 P1 marker、Make target 或 runbook 绕过识别，也不得建立第二套部署路径。
6. **Public 仓库证据边界**：Public Git 只保存非敏感资源代号、状态、不可逆哈希和私有证据引用；真实人员/名册、tenant/app ID、未公开域名/IP、ACL 明细、secret 路径内容、运行截图和业务数据进入访问受控的私有证据存储。开工前明确私有证据位置、Owner、访问范围、保留期和公开引用格式；提交前运行 secret/PII 扫描。

### 耗时口径与 WP-01 回写

WP-01 单次执行耗时 39 分 32 秒，包含合同阅读、migration/API/Web、安全负向与并发测试、19 项回归、容器重建、真实浏览器加入/退出、两项实缺陷修复、依赖审计和证据更新。对首个真实身份工作包，该时长正常，不能仅以总分钟数判定低效。

后续每个工作包分别记录 `preflight / implementation / targeted tests / browser / full gate / evidence / external wait`。完成至少三个工作包后再以中位数建立团队基线；依赖下载、registry 故障和人工等待不计入纯实现耗时。WP-01 已识别的优化是：浏览器检查前移、既有库升级测试前移、环境 bootstrap 与实现计时分离。

工具债务关闭：2026-07-21 已将 `muchen-journey-ops` 升级为 V0.3，`doctor` 可识别 `greenfield-vnext`，`status/gates` 能读取现有 WP-06/WP-07 证据并保留候选不一致、`NOT_RUN/NO_GO`；旧 P1 profile 仍独立兼容。该只读 helper 不等于实时健康检查或部署授权，生产/恢复/外部写入仍只能使用仓库已批准入口和当轮明确授权。

## 4. Definition of Ready

任务进入开发必须满足：

- [ ] 有批准的 `REQ-*` 和对应 `AT-*`；
- [ ] 用户/角色、输入、状态、权限和失败语义明确；
- [ ] 需要的 API、数据、事件和页面合同已冻结；
- [ ] 不依赖未关闭 `DEC-*`；
- [ ] 影响范围和明确非范围已列出；
- [ ] 测试数据/外部依赖可用；
- [ ] Owner 与 Reviewer 明确；
- [ ] 可在一个短生命周期分支内形成可合并结果。

缺任何一项时回到 discovery/文档，不进入编码。

## 5. Definition of Done

- [ ] 行为满足需求和体验合同；
- [ ] 数据迁移/约束/API schema 与代码同一变更提交；
- [ ] 合法、非法、权限、幂等、并发和失败测试通过；
- [ ] 无旧代码/API/DB/路由/凭证依赖；
- [ ] 日志、指标、审计和错误恢复完整；
- [ ] 可访问性和目标视口通过；
- [ ] 文档与追溯矩阵更新；
- [ ] 没有新增 TODO 式 fallback、compat、V2/P0 命名或第二状态源；
- [ ] PR Reviewer 能从 `REQ-*` 复现并验证；
- [ ] 合并后删除工作分支/worktree，记录候选影响。

## 6. Git 与分支治理

### 单一基线

- `main` 始终可部署到非生产环境；
- 受保护、禁止直接 push、禁止 force push；
- 每个 PR 从最新 main 建立，合并前 rebase/merge 更新并重跑受影响门禁；
- 候选使用不可变 tag + commit SHA + image digest；
- 不建立几十条长期 integration/rollback/lite/p0 分支。

### WIP 上限

- 每名开发者/Agent 同时最多一个实现分支；
- 全团队最多一个会修改共享合同（OpenAPI、状态机、migration 基线、auth、release）的活跃 PR；
- 同时最多一个发布候选；
- 活跃 worktree 上限为活跃贡献者数量 + 2（主线/候选）；
- 48 小时无更新的未合并 worktree 必须重新确认 Owner/下一步，否则归档；
- 候选冻结后只接受明确阻断缺陷，其他变化进入下一列车。

### 分支生命周期

- 目标 1–3 天完成；超过 3 天必须拆分或重新确认范围；
- PR 以一个可验证结果为单位；常规变更尽量控制在 Reviewer 可一次理解的规模；
- 大迁移/生成文件可例外，但手写逻辑必须拆清楚；
- 不以“每个页面一个 worktree、最后统一集成”代替领域顺序。

## 7. 共享文件与所有权

以下区域同一时刻只有一个明确 Owner：

- OpenAPI/JSON Schema；
- 领域状态机和 Current Action Resolver；
- 数据库 migration 与核心 model；
- Identity/session/permission；
- release pipeline/infra；
- 全局 design tokens/基础 UI；
- 需求追溯矩阵。

功能开发者通过提出合同变更请求协作，不在各自分支复制/绕过共享定义。

## 8. AI Agent 协作规则

鉴于上一轮产生大量 worktree/候选，Agent 工作需要额外约束：

- 每个 Agent 任务必须绑定一个 `REQ-*`、明确文件范围和完成证据；
- 任务开头必须显式说明本次使用哪些 skill、各自影响什么；若没有适用 skill，也必须说明原因。读取 instruction pack 不等于引入产品依赖；
- 修改 React/Next.js 页面、Server Action 或数据获取时使用 `vercel-react-best-practices`；真实浏览器旅程使用 `playwright`；Muchen 仓库证据/门禁/运行边界使用 `muchen-journey-ops`；
- 身份、session、权限、secret 或安全边界工作包的任务提示必须显式要求使用 `security-best-practices` 做实现复核，以满足该 skill 的触发条件；
- plugin 是承载 skill、工具或外部连接器的能力包，不是必须安装的开发组件库。只有任务确实需要对应外部系统或专用工具时才使用/安装，禁止为了“使用插件”增加依赖；
- Agent 不能自行扩大到相邻模块、部署或生产；
- 不并行修改相同共享合同；
- Agent 产出是候选 PR，不直接部署或合并 main；
- 主 Agent/Tech Lead 必须阅读差异、测试和风险，不能只接收“已完成”摘要；
- 自动生成的测试、注册表和脚本同样计入维护成本；
- 失败三次的同一集成问题停止补丁，回到合同/架构复盘；
- 每个任务结束后清理 worktree、记录 commit 和未决项。

## 9. 代码与抽象规则

- 优先清晰直接的领域代码；不建设通用平台以支持尚不存在的第二业务域；
- 两个稳定重复用例后才抽取共享组件/服务；
- 业务状态只有领域枚举；UI 禁止新增同义布尔字段；
- 禁止通用 adapter/fallback 层吞掉不一致；
- 禁止大而全 registry 作为跨域隐式总线；
- 文件变大先检查职责；不为满足行数指标机械拆文件；
- 第三方 SDK 包在 infrastructure 层，领域层不可见；
- 错误必须显式传播和分类，不默认成功；
- generated contract client 不手改；
- 测试 fixture 不进入生产 runtime。

## 10. 评审清单

### Product/Design

- 是否只解决批准的核心问题？
- 页面是否只有一个权威状态和主动作？
- 是否引入另一个入口/概念/解释层？

### Domain/Data

- 状态迁移是否合法、并发安全吗？
- 不变量是否由数据库/服务端强制？
- 是否引入历史覆盖、重复事实或第二数据源？

### API/Security

- 权限是否每次服务端校验？
- 错误、幂等、审计、敏感字段是否符合合同？
- 是否调用旧系统或复用旧凭证？

### QA/Ops

- `REQ-* → AT-*` 是否完整？
- 故障如何恢复、如何观测、如何回滚？
- 是否让 gate/harness 变得更难维护？

## 11. 进度与质量汇报

周/日汇报只跟踪：

```text
当前阶段与门禁
main SHA / 唯一 RC SHA
活跃工作包与 Owner
未关闭 BLOCKS_G0 / BLOCKS_RELEASE 决策
Sev-1/2/3 数量与趋势
主路径通过情况
隔离测试状态
唯一当前阻塞和下一步
```

不以提交数、分支数、页面数、文档数或测试数作为进度。功能完成只有通过验收并进入稳定 main 才计数。

## 12. 停止规则

发生以下任一情况，停止新增功能并复盘：

- 同类状态/身份/路由 bug 连续出现 3 次；
- 一个修复需要同时修改两套业务实现；
- 需要临时连接旧 API/DB 才能继续；
- 5 个以上活跃分支同时依赖同一共享合同（或超过团队 WIP 公式）；
- RC 冻结后 Sev-2 数量上升；
- gate 本身连续成为主要失败来源；
- 需求/数据/权限决定在编码中反复变化；
- 为赶日期提出跳过 UAT、恢复旧写入或共享旧凭证。

停止不是失败，而是阻止系统重新进入补丁螺旋。
