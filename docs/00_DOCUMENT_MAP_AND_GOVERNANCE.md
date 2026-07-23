# 00｜文档地图与治理规则

状态：`APPROVED_FOR_BUILD`  
版本：V0.2  
日期：2026-07-21  
适用阶段：立项至 G0 开工门禁  
权威性：本目录是 vNext 开发前唯一文档事实源；旧版 DOCX、旧仓库 README、会议纪要和聊天记录均不是 vNext 实施权威。

## 1. 为什么不再以“8 份文档”为目标

上一轮的问题不是文档数量不足，而是文档没有把“全新系统”转化为可机器验证的物理边界，也没有阻止实现继续依赖旧仓库、旧路由、旧数据库迁移和旧发布链路。

本轮按决策问题组织文档。每份文档必须回答一个明确问题、拥有责任人和批准状态，并能在需求、设计、代码与测试之间追溯。Word/PDF 可以作为评审导出物，但 Markdown 才是版本控制中的权威原文。

## 2. 文档清单

| 编号 | 文档 | 回答的问题 | G0 要求 |
| --- | --- | --- | --- |
| 01 | [重构失败深度复盘](01_REFACTOR_POSTMORTEM.md) | 上一轮为什么必然演化为新旧混合？ | 复盘事实无争议；纠正措施进入其他文档 |
| 02 | [Greenfield 项目章程与隔离合同](02_GREENFIELD_CHARTER_AND_ISOLATION_CONTRACT.md) | 什么叫“从零独立开发”，如何证明？ | 全部红线批准；隔离验收可执行 |
| 03 | [产品简报与 PRD](03_PRODUCT_BRIEF_AND_PRD.md) | 为谁解决什么问题，首版做什么、不做什么？ | P0 范围、角色、成功指标批准 |
| 04 | [用户旅程、信息架构与体验合同](04_USER_JOURNEYS_IA_AND_UX_CONTRACT.md) | 用户如何完成闭环，页面与状态如何组织？ | 核心旅程、路由、页面状态批准 |
| 05 | [领域模型、状态机与数据合同](05_DOMAIN_MODEL_STATE_MACHINE_AND_DATA.md) | 业务事实如何建模，谁拥有状态？ | 实体、状态迁移、数据所有权批准 |
| 06 | [系统架构与 ADR](06_SYSTEM_ARCHITECTURE_AND_ADRS.md) | 系统如何独立构建、运行和演进？ | 架构、栈、边界 ADR 批准 |
| 07 | [API、事件与集成合同](07_API_EVENT_AND_INTEGRATION_CONTRACT.md) | 前后端及外部系统如何交互？ | P0 端点、错误、幂等、集成边界批准 |
| 08 | [安全、隐私与权限模型](08_SECURITY_PRIVACY_AND_PERMISSION_MODEL.md) | 谁能看/改什么，数据如何受保护？ | 权限矩阵、敏感数据、保留规则批准 |
| 09 | [测试、UAT 与质量策略](09_TEST_UAT_AND_QUALITY_STRATEGY.md) | 如何在开发前定义“真的可用”？ | 验收场景、门禁、证据标准批准 |
| 10 | [交付计划与工程规则](10_DELIVERY_PLAN_AND_ENGINEERING_RULES.md) | 如何开发而不重演分支、补丁和并行失控？ | 里程碑、WIP、合并与 DoD 批准 |
| 11 | [发布、数据导入与运行计划](11_RELEASE_MIGRATION_AND_OPERATIONS_PLAN.md) | 如何上线、导入、观测和恢复？ | 环境、导入、切换、回滚批准 |
| 12 | [决策、风险与开放问题台账](12_DECISION_RISK_AND_OPEN_QUESTIONS.md) | 哪些决定已锁定，哪些仍阻塞开工？ | 所有 `BLOCKS_G0` 项关闭 |
| 13 | [需求追溯矩阵](13_REQUIREMENTS_TRACEABILITY_MATRIX.md) | 每条需求由什么设计、接口、数据和测试证明？ | P0 行无空白引用 |
| 14 | [UI Foundations 与组件合同](14_UI_FOUNDATIONS_AND_COMPONENT_CONTRACT.md) | 视觉、交互和组件如何保持一套正式语言？ | Token、组件状态、无障碍基线批准 |
| 15 | [P0 内容、Rubric 与运营规范](15_P0_CONTENT_RUBRIC_AND_OPERATIONS_SPEC.md) | 实际交付什么任务内容，主管按什么标准评？ | 任务/Rubric/SLA/Owner 批准 |
| 16 | [WP-00 与 Walking Skeleton 构建证据](16_WP00_AND_WALKING_SKELETON_EVIDENCE.md) | 本次实际实现、验证了什么，哪些门禁仍未运行？ | 本地基座与标准路径证据可复现；不混同发布 GO |
| 17 | [WP-01 邀请、身份与会话构建证据](17_WP01_INVITE_IDENTITY_SESSION_EVIDENCE.md) | WP-01 实际实现和自动化证明了什么，哪些真人/物理门禁仍未运行？ | 邀请、内部身份、独立会话证据可复现；不混同 UAT/发布 GO |
| 18 | [WP-02 Current Action 与任务版本构建证据](18_WP02_CURRENT_ACTION_TASK_VERSION_EVIDENCE.md) | WP-02 的 Resolver、任务版本、Learner 页面和迁移实际证明了什么？ | Current Action/TaskVersion 证据可复现；真人理解率与发布门禁仍独立 |
| 19 | [WP-03 提交、附件与修订构建证据](19_WP03_SUBMISSION_ATTACHMENT_REVISION_EVIDENCE.md) | WP-03 的不可变提交历史、受控附件、草稿恢复与首次/修订路径实际证明了什么？ | REQ-BR-004/006 本地证据可复现；真人 UAT、真实存储/扫描和发布门禁仍独立 |
| 20 | [WP-04 Reviewer 工作台与结论构建证据](20_WP04_REVIEWER_WORKBENCH_EVALUATION_EVIDENCE.md) | WP-04 的授权队列、固定材料、结构化结论、不可变历史与 Learner 状态闭环实际证明了什么？ | REQ-BR-005 本地证据可复现；真人 Reviewer/UAT、校准、物理环境和发布门禁仍独立 |
| 21 | [WP-05 结果、交接、通知与历史构建证据](21_WP05_OUTCOME_HANDOFF_NOTIFICATION_TIMELINE_EVIDENCE.md) | WP-05 的不可变 Outcome/Handoff、可重试通知 worker、完整结果页与跨域时间线实际证明了什么？ | REQ-BR-007/009/010 本地证据可复现；真实通知/AI、真人 UAT、物理环境和发布门禁仍独立 |
| 22 | [WP-06 受控运营、离线导入、恢复与发布门禁构建证据](22_WP06_CONTROLLED_OPERATIONS_IMPORT_RECOVERY_RELEASE_EVIDENCE.md) | WP-06 的有意图运营命令、签名导入、安全审计、运行状态、本地灾备及 fail-closed 发布判断实际证明了什么？ | REQ-BR-008、ISO-MUST-009/010/011 与 NFR-009/010/011 本地证据可复现；真实导入、真人 UAT、真实通知、物理环境、异机恢复和发布签署仍 `NOT_RUN`/`NO_GO` |
| 23 | [G4–G6 下一批工作包定义](23_G4_G6_NEXT_WORK_PACKAGES.md) | WP-07～WP-15 如何按单一 WIP 推进候选、试点与正式切换？ | 已升级 `APPROVED_FOR_BUILD`；WP-07 已关闭，当前仅 WP-08 活跃且最小部署通道修复已就绪；WP-09～WP-15 未激活，真人/时间/production 边界仍独立 |
| 24 | [WP-07 候选基线与软件供应链构建证据](24_WP07_CANDIDATE_BASELINE_SUPPLY_CHAIN_EVIDENCE.md) | 本地候选、分层 CI、扫描、SBOM 与 release manifest 实际证明了什么？ | 候选、远端 CI、GHCR digest 与受保护 main 已复验；staging/production 仍不在该证据范围 |
| 25 | [WP-08 Definition of Ready 构建证据](25_WP08_DEFINITION_OF_READY_EVIDENCE.md) | 物理 staging 写入前的 Git、浏览器、迁移、fixture、冷启动、Ops 与证据边界是否真实可重复？ | 本地 DoR 证据可复现；不等同于物理 staging 已创建、部署或通过隔离验收 |
| 26 | [WP-08 火山引擎 Staging 实施路径证据](26_WP08_VOLCENGINE_STAGING_PATH_EVIDENCE.md) | 已锁定 provider/region/budget 后，唯一 IaC/CI/secret/回滚路径是什么，云端是否已经写入？ | provision 已收敛且新 RDS CA 已写入 staging Environment；最小部署通道修复不新增资源/IAM，等待受保护主线复验和新的单次 deploy |

## 3. 权威顺序

发生冲突时按以下顺序处理：

1. 已批准的 `DEC-*` 决策；
2. Greenfield 隔离合同；
3. 已批准的 PRD 与体验合同；
4. 领域、架构、API、安全合同；
5. 测试、交付和运行计划；
6. 需求追溯矩阵；
7. 原型、任务单和实现说明。

任何人不能通过代码、临时脚本、环境变量或发布操作悄悄改变上位合同。需要改变时，先更新决策及受影响文档，再改实现。

## 4. 文档状态

| 状态 | 含义 |
| --- | --- |
| `DRAFT_FOR_APPROVAL` | 内容已准备，尚未获得责任人批准 |
| `BLOCKED_BY_DECISION` | 存在会改变实现方向的未决事项 |
| `APPROVED_FOR_BUILD` | 已批准，可作为开发输入 |
| `SUPERSEDED` | 已被明确的新版本替代，保留追溯 |
| `AS_BUILT` | 记录已实现事实；必须注明验证环境和发布状态，不得覆盖原设计版本 |

设计文档和 As-Built 记录必须分版保存。禁止像上一轮一样把生产补遗继续追加到原始设计稿并让两者共用同一版本身份。

## 5. 变更规则

- 每个 P0 需求使用永久 `REQ-*` 编号；每个决策使用永久 `DEC-*` 编号；每个验收使用永久 `AT-*` 编号。
- 变更必须说明原因、影响的需求/状态/API/数据/测试、批准人和生效版本。
- 一个需求若无法映射到验收场景，不得进入开发。
- 一个实现若无法映射到批准需求，不得合并。
- 口头决定、聊天内容和代码注释只有被登记后才生效。
- 文档与代码在未来独立仓库内一起评审；本预备包获批后整体迁入该仓库。

## 6. G0 开工门禁

以下条件全部满足后，才允许初始化产品脚手架：

- [x] `DEC-001` 至 `DEC-016` 中所有适用的构建方向已批准；需真人或物理环境证明的项目转为 G4/G5 门禁，不得伪造证据。
- [x] P0 只有一个明确垂直闭环，范围和非目标已批准。
- [x] 新仓库及全部独立资源命名和初始 Owner 已确定；物理 staging/prod 资源在 G4 验证。
- [x] 旧仓库依赖禁令、旧数据库网络禁令和离线导入边界已写成可执行验收。
- [x] P0 状态机不存在同义状态或“兼容状态映射”。
- [x] API、权限、错误、幂等和审计合同已冻结。
- [x] `REQ-* → AT-*` 追溯完整；真实角色 UAT 规模和角色已安排，具体名册在 G4 受控登记。
- [x] P0 不导入旧业务数据；未来导入必须离线、隔离、可拒绝且零写回。
- [x] 发布、回滚、备份恢复和观测初始责任人已确认；真人/物理演练仍是 G4 门禁。
- [x] 本轮批准明确接受：进度压力不能豁免隔离红线。

## 7. G0 签署角色

| 角色 | 责任 |
| --- | --- |
| Product Owner | 产品问题、P0 范围、角色、内容和成功指标 |
| Tech Lead | Greenfield 边界、架构、API、工程门禁 |
| Data Owner | 新数据模型、导入范围、核对与保留 |
| Design Owner | 用户旅程、IA、页面状态和可访问性 |
| Security/Privacy Owner | 身份、权限、敏感数据、审计与数据权利 |
| QA/UAT Owner | 验收场景、真实角色、证据和退出标准 |
| Release/Ops Owner | 环境、部署、观测、恢复和切换 |

同一人可以承担多个角色，但每项责任必须明确写出姓名，不能只写“产品团队”或“研发团队”。
