# 12｜决策、风险与开放问题台账

状态：`APPROVED_FOR_BUILD`  
版本：V0.1  
日期：2026-07-20  
文档 Owner：Product Owner（业务）+ Tech Lead（技术）  
规则：`BLOCKS_G0` 未关闭即 No-Go；不得用“先按默认做，后面再调”开始编码。

## 1. 状态定义

| 状态 | 含义 |
| --- | --- |
| `LOCKED_BY_DIRECTION` | 已由本轮明确方向锁定，待责任人补正式签署 |
| `PROPOSED` | 本文给出建议，尚未批准 |
| `NEEDS_DISCOVERY` | 缺事实/原型/业务输入，必须先调研 |
| `APPROVED` | 已批准并可约束开发 |
| `REJECTED` | 已拒绝，记录替代方案 |
| `SUPERSEDED` | 被新 DEC 明确替代 |

## 2. 决策台账

| ID | 决策 | 已批准结论 | 状态 | 门禁 | Owner |
| --- | --- | --- | --- | --- | --- |
| DEC-001 | 项目类型 | vNext 是 Greenfield Replacement，不是止血重构、旁路 V2 或渐进兼容 | `APPROVED` | `BUILD_G0` | Liu Mowen（初始 Product + Tech Owner） |
| DEC-002 | 旧系统边界 | 旧系统仅用于需求调研、只读归档和离线导出；无运行时依赖/写回/回滚 | `APPROVED` | `BUILD_G0` | Liu Mowen（初始 Product + Tech + Data Owner） |
| DEC-003 | 独立资源 | 资源统一使用 `journey-next-*` 命名；本仓库、独立 DB/bucket/identity/CI/CD/secret/observability 不与旧系统共享 | `APPROVED` | `BUILD_G0`；物理生产验证 `G4` | Liu Mowen（初始 Tech + Ops Owner） |
| DEC-004 | P0 范围 | 只做探索营邀请→任务→提交→主管评审→修订/通过→结果/交接；只含 TSK-001 | `APPROVED` | `BUILD_G0` | Liu Mowen（Product Owner） |
| DEC-005 | 技术栈 | Next.js 16 + TypeScript、FastAPI 0.139 + Python 3.14、PostgreSQL、S3-compatible storage；全新初始化 | `APPROVED` | `BUILD_G0` | Liu Mowen（Tech Owner） |
| DEC-006 | 身份方案 | 采用 C：邀请建立 vNext 内部身份与独立会话；Reviewer/Operator 在非本地环境绑定独立飞书身份 | `APPROVED` | `BUILD_G0` | Liu Mowen（Product + Security Owner） |
| DEC-007 | 首批试点 | 5 名新人、2 名独立主管、1 名运营、1 名 QA Recorder；使用专用账号与受控人员名册 | `APPROVED` | 人员名册与真人执行 `G4` | Liu Mowen（Product + QA Owner） |
| DEC-008 | 数据治理 | 身份/提交/评价/结果保留 3 年，附件 1 年，通知元数据 180 天，幂等记录 30 天，审计 3 年；删除请求 30 天内处理，法定保留除外 | `APPROVED` | `BUILD_G0` | Liu Mowen（Privacy + Data Owner） |
| DEC-009 | 历史数据导入 | P0 不导入旧业务事实；所有试点对象在 vNext 新建。未来导入需新 DEC 与离线签名包 | `APPROVED` | `BUILD_G0` | Liu Mowen（Product + Data Owner） |
| DEC-010 | 成功与观察 | 14 天试点；完成率≥80%、当前行动理解率≥90%、90% 评审在 2 个工作日内、重复事实/状态冲突为 0、支持介入率≤20% | `APPROVED` | 实测与观察 `G5` | Liu Mowen（Product + QA Owner） |
| DEC-011 | 通过后的下一步 | 产生 `HANDOFF_READY`，展示责任人和说明；不调用旧新手村 API，不共享会话或状态 | `APPROVED` | `BUILD_G0` | Liu Mowen（Product Owner） |
| DEC-012 | AI Advisor | 不进入 P0；无模型调用、无 AI 数据处理 | `APPROVED` | `BUILD_G0` | Liu Mowen（Product + Security + Tech Owner） |
| DEC-013 | SLO/恢复预算 | 常规 API p95≤1 秒；试点可用性 99.5%；RPO≤24 小时、RTO≤4 小时；每日备份、月度隔离恢复、14 天观察 | `APPROVED` | 演练证据 `G4` | Liu Mowen（Tech + Ops + Data Owner） |
| DEC-014 | 生产控制 | 生产密钥仅在受管 secret store；CI 受限身份发布；个人机器不得直接生产部署；双人批准后开放写入 | `APPROVED` | 物理配置与人员授权 `G4` | Liu Mowen（初始 Security + Ops Owner） |
| DEC-015 | UI Foundations | 系统字体、4px 网格、390/768/1280、WCAG 2.2 AA、单一正式组件与蓝色主操作语义 | `APPROVED` | `BUILD_G0` | Liu Mowen（初始 Design + Frontend Owner） |
| DEC-016 | P0 内容与评审 | 只发布 TSK-001“问题洞察与行动建议”；四维 Rubric 全部达标才 PASS；Reviewer SLA 2 个工作日 | `APPROVED` | 真人校准 `G4` | Liu Mowen（初始 Product + Content + Reviewer Owner） |

> Owner 说明：仓库使用操作系统账号对应的项目发起人标识 `Liu Mowen` 作为初始责任人。真实试点参与者采用受控名册，不把姓名或外部身份标识提交到 Git。真人 UAT、Reviewer 独立性和生产双人批准必须在 G4 以独立证据确认，当前均为 `NOT_RUN`。

## 3. 决策说明与选择框架

### DEC-004｜为什么推荐只做探索营

上一轮同时承载探索营、新手村、AI 学院、Talent OS 和旧后台，导致路由、权限、状态和验收呈乘法增长。探索营具备清晰的真实新人 + 真实主管闭环，足以验证 Identity、Assignment、Submission、Review、Outcome、Notification 和运维基础，不需要先建立多空间平台。

若 P0 加入第二空间，Product Owner 必须证明它是同一闭环不可缺的步骤，而不是“既然重做顺便一起做”。

### DEC-005｜同栈不等于同系统

继续使用相同公开技术栈可降低团队学习成本，但必须通过新 repo、空白配置、新迁移、独立资源和禁止源码复用证明独立。如果技术 discovery 发现当前栈本身无法满足团队能力/部署/性能，再用小原型比较，而不是通过换栈掩盖边界问题。

### DEC-006｜身份选择标准

比较：用户进入阻力、是否必须企业飞书身份、非员工/候选人适用性、主管授权来源、安全与运营成本。无论选择哪一项，vNext 内部 UUID 和独立 session 不变。

### DEC-011｜交接不应重新耦合旧系统

P0 可以输出“handoff ready + 明确责任人/说明/外部链接”，但不能为了自动进入旧新手村而在 vNext 引入旧 API、旧 session 或共享状态。未来后续系统集成需独立 ADR/API 合同。

## 4. 风险台账

| ID | 风险 | 概率/影响 | 早期信号 | 预防/缓解 | Owner |
| --- | --- | --- | --- | --- | --- |
| RSK-001 | 范围重新扩到多空间/平台 | 高/高 | PRD 出现 Academy/Village/Registry 空框架 | DEC-004；非目标；G0/DoR 拒绝 | Product |
| RSK-002 | 偷偷复用旧代码/适配器 | 高/高 | import、复制文件、旧 env/URL 出现 | ISO scan；空 runner；code review | Tech |
| RSK-003 | 新库仍连接/复制旧 schema | 中/高 | migration 从 0017 继续、旧表名/enum | 独立 DB ACL；0001；schema review | Data/Tech |
| RSK-004 | 旧系统变成 fallback | 高/高 | 错误时建议回旧页面/恢复旧写入 | DEC-002；网关外部切换；rollback 演练 | Product/Ops |
| RSK-005 | 身份方案迟迟变化 | 高/高 | join/SSO/绑定页面反复重写 | DEC-006 先做真实 prototype/discovery | Product/Security |
| RSK-006 | 历史导入拖垮新模型 | 高/高 | 要求 1:1 搬表、在线双读 | DEC-009；中性包；quarantine | Data/Product |
| RSK-007 | Agent/分支并行失控 | 高/高 | 多 worktree 改共享合同、候选漂移 | WIP 上限；单 Owner；唯一 RC | Tech |
| RSK-008 | 验收 harness 再次膨胀 | 中/高 | 单个 smoke 上千行、失败归属不明 | 小 runner + 场景文件；分层 gate | QA/Tech |
| RSK-009 | 时间压力绕过 G0/UAT | 高/高 | “先上线再补文档/真实用户” | No-Go 清单；Owner 签字；日期服从门禁 | Product |
| RSK-010 | 真用户/主管不可用 | 中/高 | 自动化全绿但无人做 UAT | DEC-007 在 G0 锁人和时间 | Product/QA |
| RSK-011 | 主管权限/班级 scope 不清 | 中/高 | 前端筛选代替后端授权 | 权限矩阵；真实组织样本；负向测试 | Product/Security |
| RSK-012 | AI 引入隐私/结论风险 | 中/高 | 完整正文发送、AI 结果直接 PASS | DEC-012；advisory-only；数据最小化 | Security/Tech |
| RSK-013 | 独立基础设施无人维护 | 中/高 | 新 env/备份/告警长期 TBD | DEC-003/013/014 指名 Owner | Ops |
| RSK-014 | 同栈导致无意识复制旧模式 | 中/高 | route registry、adapter、P0/V2 命名重现 | ADR review；forbidden pattern scan | Tech |
| RSK-015 | 过度文档化、决定仍不落地 | 中/中 | 文档更多但 TBD 不关闭 | G0 只看阻塞项和签署；限时决策会 | Product/Tech |
| RSK-016 | 新系统上线后 bug 继续上升 | 中/高 | RC 后 Sev-2 增长、同类 bug 3 次 | 停止规则；根因/门禁复盘；冻结功能 | QA/Tech |

## 5. 原开放问题的关闭结论

| 原问题组 | 关闭结论 | 约束来源 |
| --- | --- | --- |
| 产品闭环、结果与成功标准 | 只做探索营 TSK-001；通过后仅生成 `HANDOFF_READY`；按 14 天试点阈值判断 | DEC-004/010/011/016 |
| 身份与权限 | 邀请建立 vNext 身份；非本地 Reviewer/Operator 绑定独立飞书身份；Reviewer 按 organization + explicit assignment 授权；紧急纠错需 Operator 原因与审计 | DEC-006/014；08 号文档 |
| 数据与旧数据 | P0 对象全部新建，不导入旧业务事实或附件；保留/删除期限按 DEC-008 | DEC-008/009 |
| 技术、资源与运行 | 使用批准栈和 `journey-next-*` 独立资源；AI 不进 P0；SLO/RPO/RTO 与生产权限已锁定 | DEC-003/005/012/013/014 |
| UI、内容与运营 | 使用批准 UI tokens；仅 TSK-001/Rubric V1；两工作日 SLA；版本化发布和撤销 | DEC-015/016；14/15 号文档 |
| 真人和物理证据 | 真实名册、资源 ACL、双人批准、恢复演练、UAT 与试点结果不是开放设计问题，作为 G4/G5 `NOT_RUN` 执行门禁保留 | DEC-003/007/010/013/014/016 |

## 6. G0 批准记录

2026-07-20 已完成构建方向批准：DEC-001–016 全部为 `APPROVED`。本次批准授权建立独立仓库、WP-00 与最小 walking skeleton；不授权绕过 G4/G5 的真人、生产、恢复或发布证据，也不扩大为同时建设全部 P0 模块。

## 7. 签署区

| 角色 | 姓名 | 已批准 DEC | 未批准 DEC | 结论 | 日期 |
| --- | --- | --- | --- | --- | --- |
| Product Owner | Liu Mowen | DEC-001..016 | 真人试点结果 | BUILD GO | 2026-07-20 |
| Tech Lead | Liu Mowen | DEC-001..016 | 物理生产资源验证 | BUILD GO | 2026-07-20 |
| Data Owner | Liu Mowen | DEC-001..016 | 恢复演练证据 | BUILD GO | 2026-07-20 |
| Design Owner | Liu Mowen | DEC-015/016 | 真人 5 秒测试 | BUILD GO | 2026-07-20 |
| Security/Privacy | Liu Mowen | DEC-006/008/012/014 | 生产安全门禁 | BUILD GO | 2026-07-20 |
| QA/UAT | Liu Mowen | DEC-007/010/016 | 真人 UAT | BUILD GO | 2026-07-20 |
| Release/Ops | Liu Mowen | DEC-003/013/014 | 发布/观察证据 | BUILD GO | 2026-07-20 |
