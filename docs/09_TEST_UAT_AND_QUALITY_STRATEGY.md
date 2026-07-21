# 09｜测试、UAT 与质量策略

状态：`APPROVED_FOR_BUILD`  
版本：V0.2  
日期：2026-07-20  
文档 Owner：QA/UAT Owner + Tech Lead  
质量原则：测试要证明一个小系统真实成立，不再为多代兼容系统建立不断膨胀的门禁矩阵。  
变更说明：根据 WP-01 实测，增加既有开发库升级路径、早期浏览器检查和单工作包门禁顺序。

## 1. 质量目标

- 每个 P0 需求在开发前有可执行验收；
- 每个状态迁移、权限判断、幂等/并发不变量都有自动化证明；
- 真实用户体验由真实角色 UAT 证明，不能由 selector 或 mock 替代；
- Greenfield 独立性有专门断依赖测试；
- 快速开发反馈与完整发布证据分层；
- bug 修复减少未知风险，不新增长期补丁路径。

## 2. 测试分层

| 层 | 目标 | 典型内容 | 运行时机 |
| --- | --- | --- | --- |
| Domain | 证明纯业务规则 | 状态转换、resolver、不变量、权限策略、幂等 hash | 每次提交/PR |
| Persistence | 证明真实约束 | 唯一/外键/事务/并发、迁移、outbox | PR/主线 |
| API Contract | 证明协议 | OpenAPI、错误码、auth、合法/非法命令 | PR/主线 |
| Component/UI | 证明页面状态 | 表单校验、焦点、错误恢复、单 CTA | PR |
| Browser Journey | 证明真实闭环 | 标准路径、修订路径、三视口、键盘 | 主线/候选 |
| Integration | 证明外部边界 | 飞书、对象存储、AI 降级、worker | 候选/发布 |
| Isolation | 证明独立性 | 无旧 repo、旧 DB、旧 API、旧凭证 | 主线/候选 |
| UAT | 证明产品有效 | 真实新人、主管、运营完成真实任务 | 候选/试点 |
| Operability | 证明能运行 | 部署、备份恢复、告警、回滚、导入 | 发布前 |

## 3. 必测业务矩阵

### 身份与邀请

- 有效、过期、撤销、已消费邀请；
- 同一 token 并发消费；
- 新用户、已有 vNext 用户、停用用户；
- 旧 session/token 被拒绝；
- 恶意 return URL、state 重放、CSRF；
- 无效邀请不产生孤儿 Enrollment。

### Assignment 与提交

- AVAILABLE → IN_PROGRESS；非法状态 start；
- 首次提交、超时重试、相同 key 不同正文；
- expected revision 冲突且草稿不丢；
- 附件未 READY、跨 owner、超大/非法类型；
- NEEDS_REVISION 再提交；旧版本保持不变；
- 两个浏览器窗口并发操作。

### Review

- 授权队列、直接 URL 越权、跨组织；
- GET 无副作用；start 幂等；
- Rubric/证据缺失阻断 finalize；
- 两个 reviewer/窗口同时 finalize；
- PASS 与 REVISION_REQUIRED；
- AI 不可用时人工照常完成；
- finalized 不可通用 reopen。

### Outcome 与异步

- PASS 后 Evaluation、Assignment、Outcome 和 Current Action 一致；
- 下一步创建失败可恢复且只创建一次；
- 飞书通知失败/重试/DEAD 不改变业务事实；
- worker 中断重启不重复消费；
- 结果刷新、跨设备读取一致。

### Operator/Admin

- 邀请、撤销、分配 reviewer、取消 Enrollment；
- 所有命令要求 scope、reason 和审计；
- 无通用 status 编辑；
- 异常数据进入明确处理队列，不静默修复。

## 4. Greenfield 独立性测试

隔离测试是一等门禁，不是文档检查：

- 构建容器中不挂载旧仓库；
- egress deny 旧 API/DB/storage 域名/IP；
- 使用只对 vNext DB 有权限的 role；
- 扫描 import、URL、env、路由、migration 中的旧系统标识；
- 旧系统停机时跑完整 browser/UAT fixture；
- 旧凭证请求 vNext 返回 401/403；
- vNext rollback 不执行旧部署或旧 DB 写入；
- 离线导入环境不访问旧网络。

## 5. 测试数据

- 自动化使用 vNext 独立 fixture factory，不复用旧 mock/seed；
- 每个场景显式创建 organization、用户、scope、任务版本和状态；
- 不通过修改数据库 status 跳过前置步骤，除非测试的就是数据修复/迁移；
- 新 migration/seed 同时验证两条路径：从空库构建，以及从上一工作包的持久开发库升级；seed 必须增量、幂等，不能因基础实体已存在而跳过新工作包必需 fixture/config；
- 生产 UAT 使用专门账号、可识别批次和可回收但可审计的数据；
- 生产只读检查不能冒充完成真实写路径 UAT；
- 测试数据不得含真实无关 PII/客户材料。

## 6. UAT 计划

### 角色

| UAT 角色 | 要求 |
| --- | --- |
| 真实新人 | 首次接触或仅获得标准邀请说明；不能由开发代操作 |
| 独立主管 | 使用自己的授权账号；不能与新人共享身份 |
| 运营 | 创建邀请、分配主管、观察异常与通知 |
| QA Recorder | 记录时间、操作、request id、困惑和结果，不替用户解释 |
| Product Owner | 判断产品问题和是否接受 |

### 场景

- `AT-UAT-001`：标准通过路径端到端；
- `AT-UAT-002`：需要修订再通过；
- `AT-UAT-003`：邀请/身份异常恢复；
- `AT-UAT-004`：提交超时与冲突恢复；
- `AT-UAT-005`：主管材料缺失与越权拒绝；
- `AT-UAT-006`：通知失败但业务可见；
- `AT-UAT-007`：390/768/1280 与纯键盘主路径；
- `AT-UAT-008`：运营定位并处理一个受控异常。

### 记录字段

release revision、环境、角色/账号标识（最小化）、场景、开始/结束时间、实际步骤、结果、截图/录像引用、request id、是否需要帮助、困惑、缺陷 ID、签署人。

## 7. 门禁分层

### 单工作包的本地验证顺序

1. 开工前完成一次依赖/镜像 bootstrap，并把下载等待与实现耗时分开记录；
2. 先跑受影响的 Domain/Persistence/API/Component 定向测试，保持短反馈；
3. 第一条端到端路径可用后立即跑真实浏览器 smoke，再整理 OpenAPI 和 As-Built 证据；涉及 URL fragment、cookie、hydration、重定向或焦点时不得只靠 API/production build 推断正确；
4. 定向与浏览器检查稳定后运行一次完整 `make verify`、依赖审计和容器 smoke；完整门禁通过后若代码再变化，最终只补跑受影响层并在交付前再运行一次完整门禁；
5. 外部 registry/网络失败单独记为环境等待，不修改代码、不放宽门禁；确认没有产品执行后允许一次原命令重试。

禁止在真实浏览器主路径尚未验证时先写“已通过”证据，也禁止没有代码变化却重复运行完整门禁追求仪式性绿灯。

### PR 快速门禁（目标 ≤ 10 分钟）

- 格式/类型/静态检查；
- 受影响 Domain、Persistence、API、Component 测试；
- contract diff 与 migration lint；
- dependency/secret/legacy reference scan；
- 需求/测试 ID 追溯检查。

### 主线门禁

- 全量 Domain/API/DB；
- 从空库迁移；
- 核心 browser 标准/修订路径；
- isolation/permission/security 负向测试；
- 构建与容器 smoke。

### 发布候选门禁

- 精确候选 revision 的完整 browser/integration；
- 三视口/键盘/浏览器矩阵；
- 飞书、对象存储、AI 降级与 worker；
- 性能/可靠性、导入演练、备份恢复、回滚；
- 真实角色 UAT 和签字。

### 生产发布门禁

- 候选 revision、镜像 digest、migration、环境清单一致；
- 只读 preflight；
- 备份和恢复证据仍有效；
- 部署后健康、合成 smoke、关键业务只读/专用测试；
- 观察窗口满足退出条件。

禁止把全部发布检查串进每次本地开发；也禁止用快速门禁替代候选/生产门禁。

## 8. 缺陷等级

| 等级 | 定义 | 处理 |
| --- | --- | --- |
| Sev-1 | 数据泄露/丢失、跨组织越权、无法安全恢复、广泛不可用 | 立即停止发布/写入，启动事故流程 |
| Sev-2 | P0 主路径失败且无安全 workaround；重复/错误业务事实 | 候选 NO-GO，修复并完整回归 |
| Sev-3 | 有安全 workaround，不破坏事实/权限但影响效率或理解 | Product/QA 书面接受，明确 Owner/期限 |
| Sev-4 | 非阻断视觉/文案问题 | 排期，不为凑版本现场补丁 |

## 9. Bug 修复合同

每个 bug 在合并前必须回答：

1. 复现条件和受影响 `REQ-*`/状态/角色是什么？
2. 根因在需求、设计、代码、数据、环境还是测试？
3. 为什么现有门禁未发现？
4. 新增哪一个最小回归测试？
5. 修复是否增加兼容分支、fallback 或第二事实源？如是则拒绝并重设计。
6. 该类问题是否需要修订上位合同？

不得通过扩大 try/catch、默认成功、隐藏错误、跳过门禁、放宽权限或复制组件快速转绿。

## 10. 测试代码治理

- 场景数据与 runner 分离；runner 保持通用且小；
- 不建立单个数千行全站 smoke；按领域场景组合；
- 一个测试只证明清晰风险，失败消息指出 Owner/场景/实际差异；
- 禁止 snapshot 大面积更新掩盖行为变化；
- flaky 测试视为缺陷：隔离、定责、修复，不无限重跑；
- 环境不满足时明确 `SKIPPED_WITH_REASON`，不能记 PASS；
- 每季度/阶段删除已无需求依据的测试和 fixture。

## 11. 发布退出标准

- [ ] P0 需求和状态迁移 100% 场景覆盖；
- [ ] 权限正/负向、幂等、并发、旧依赖阻断全部通过；
- [ ] Sev-1/Sev-2 = 0；
- [ ] 主线连续稳定，候选冻结后无漂移；
- [ ] 真实标准/修订路径通过且有证据；
- [ ] 备份恢复、导入、回滚、告警演练通过；
- [ ] 失败/跳过项被清楚记录并由相应 Owner 签署；
- [ ] bug 趋势未在候选后继续上升。
