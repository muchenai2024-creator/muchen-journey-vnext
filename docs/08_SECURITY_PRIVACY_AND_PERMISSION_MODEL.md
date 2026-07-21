# 08｜安全、隐私与权限模型

状态：`APPROVED_FOR_BUILD`  
版本：V0.1  
日期：2026-07-20  
文档 Owner：Security/Privacy Owner + Tech Lead  
批准基线：邀请身份 + 后续飞书绑定；独立对象存储与密钥命名空间；保留期限按 DEC-008；物理生产配置在 G4 验证。

## 1. 保护目标

- 只有正确身份在正确组织/批次/对象范围内访问数据；
- 邀请、会话、附件和评审不能被猜测、重放或横向越权；
- 新人提交和主管反馈不因日志、通知、AI 或分析而扩散；
- 人工结论、不可变历史和审计不能被静默覆盖；
- vNext 与旧系统凭证、会话、数据库和对象存储完全隔离；
- 高风险运营行为有最小权限、理由、审计和恢复程序。

## 2. 信任边界

| 边界 | 不可信输入 | 必须控制 |
| --- | --- | --- |
| 浏览器 → Web/API | 参数、cookie、文件、富文本、重试 | 认证、CSRF、验证、编码、限流、幂等 |
| API → PostgreSQL | 应用命令、查询条件 | 参数化、事务、组织 scope、最小 DB role |
| API → Object Storage | 文件元数据、download request | owner/purpose、hash、类型、短时 URL |
| Worker → 飞书/AI | recipient、模板、正文 | allowlist、最小数据、重试、脱敏、审计 |
| Operator/Admin → 业务命令 | 高权限纠错 | RBAC + scope + reason + audit + 二次确认 |
| 离线导入包 → Importer | 旧数据、恶意/异常内容 | 签名/checksum、schema、隔离、计数、幂等 |
| vNext → 旧系统 | 任何网络请求 | 默认拒绝；没有运行时合同 |

## 3. 身份与会话

- 内部 `user_id` 是唯一业务身份；第三方 subject 只做映射；
- dev/test/staging/prod 使用不同身份 app、callback 和 secret；
- session cookie：Secure、HttpOnly、适当 SameSite、短期有效、可撤销；
- 登录/绑定 state 一次性且防重放；return URL 严格 allowlist；
- 权限/停用变更后旧会话在可接受窗口内失效；
- 不接受旧系统 cookie、JWT、Bearer token 或共享 secret；
- 不在 localStorage/sessionStorage 保存 session/token；
- 管理员不使用默认密码或共享账号；生产要求个人身份和最小权限。

## 4. 权限模型

权限判断至少包含：actor 状态、organization、role、scope、resource owner/assignment、命令、当前状态。

| 能力 | Learner | Reviewer | Operator | Admin |
| --- | --- | --- | --- | --- |
| 查看本人 Current Action | 自己 | 否 | 仅授权支持视图 | 仅审计/支持授权 |
| 查看/提交 Assignment | 自己 | 只读被分配提交 | 仅状态摘要 | 受控支持，不代提交 |
| 查看 Review | 本人的已发布反馈 | 明确分配给自己 | 授权批次摘要 | 授权范围 |
| 开始/finalize Review | 否 | 明确分配且有效 | 否 | 默认否；紧急纠错走独立命令 |
| 创建/撤销 Invite | 否 | 否 | 授权组织/批次 | 是，仍需 scope |
| 分配 Reviewer | 否 | 否 | 授权组织/批次 | 是 |
| 发布 TaskVersion | 否 | 可参与内容评审，不直接发布 | 指定内容 Owner | 指定 Admin |
| 查看审计 | 本人可见事件摘要 | 本人相关摘要 | 授权运营审计 | 安全/管理员范围 |
| 导出数据 | 否 | 否 | 默认否/审批 | 单独权限 + 审批 + 审计 |

规则：前端隐藏只是体验，API 必须重新授权。对可能泄露资源存在性的越权请求使用 404 或等价安全响应。

## 5. 主要威胁与控制

| 威胁 | 场景 | 控制 | 测试 |
| --- | --- | --- | --- |
| 邀请窃取/重放 | token 被转发、日志泄漏、重复消费 | 高熵随机、存 hash、短有效期、一次消费、撤销、日志脱敏 | `AT-SEC-001` |
| IDOR | 修改 URL 查看他人任务/评审/附件 | 每次读取按 actor + org + resource 授权；不可枚举 ID | `AT-SEC-002` |
| 跨组织访问 | reviewer/ops 查看其他组织 | scope 强制、复合约束/查询封装、负向测试 | `AT-SEC-003` |
| 会话攻击 | fixation、旧 session、CSRF、开放重定向 | session rotation、CSRF、SameSite、state、return allowlist、撤销 | `AT-SEC-004` |
| 文件攻击 | 恶意类型、超大文件、越权下载 | 大小/类型/hash、隔离扫描、短时 URL、重新授权 | `AT-SEC-005` |
| 注入/XSS | 任务正文、反馈、导入内容含恶意输入 | 参数化查询、输出编码、富文本 allowlist/CSP | `AT-SEC-006` |
| 并发越权 | 两人同时 finalize 或重放命令 | revision、唯一约束、幂等、事务 | `AT-SEC-007` |
| 通知泄漏 | 错发给其他主管/组织 | 验证身份映射、recipient scope、模板最小化、投递审计 | `AT-SEC-008` |
| AI 数据泄漏/越权 | 发送不必要 PII、AI 自动定结论 | 数据最小化、供应商审批、advisory-only、人工 finalize | `AT-SEC-009` |
| 日志泄密 | token、正文、附件、手机号进入日志 | 结构化日志 allowlist、redaction、release scan | `AT-SEC-010` |
| 管理员滥用 | 直接改状态/覆盖历史 | 无通用 PATCH/SQL UI；业务命令、reason、审计、告警 | `AT-SEC-011` |
| 旧系统横向移动 | 复用旧密钥/网络导致跨系统访问 | 独立 secret/role/network；egress deny；凭证互斥 | `AT-SEC-012` |
| 导入污染 | 旧数据伪造/歧义/重复 | 签名 checksum、schema、quarantine、幂等、人工裁决 | `AT-SEC-013` |

## 6. 数据最小化与隐私

每个字段在 schema 评审时登记：用途、Owner、敏感级别、可见角色、保留期、删除/匿名化方式、是否进入日志/事件/分析/AI。

默认原则：

- 没有明确用途不采集；
- 手机、邮箱、飞书 subject 等只在必要模块保存；
- 任务正文与附件不进入通用分析事件；
- 审计记录动作和引用，不复制完整敏感正文；
- AI 输入使用最小片段并记录用途/版本，不默认用于供应商训练；
- 导出需要单独权限、审批、范围和过期控制；
- 账号停用、访问到期、数据删除、法定/审计保留分别建模；
- 用户纠错/删除请求有可执行流程和审计。

批准期限：身份、提交、评价、结果和审计保留 3 年；附件保留 1 年；通知投递元数据保留 180 天；幂等记录保留 30 天。用户删除/纠错请求在 30 天内处理，法定、争议或安全审计保留除外。

## 7. 密钥与环境

- 密钥只在受管 secret store/CI secret 中；不写入 repo、镜像、构建产物或日志；
- 各环境 secret 完全不同；生产 secret 不进入开发机和浏览器 bundle；
- DB role 只访问 vNext 数据库；迁移 role 与运行 role 分离；
- Worker 第三方凭证按用途分离；
- 生产发布使用受限身份，不使用 root/个人长期密钥；
- 密钥轮换、吊销和泄露处置需要演练；
- 旧系统 secret 不复制到 vNext。

## 8. 审计与告警

必须审计：登录/绑定/退出、权限拒绝、邀请创建/消费/撤销、主管分配、提交、评审开始/finalize、TaskVersion 发布、取消/纠错、导入/导出、Admin/安全配置、密钥或角色变更。

告警至少覆盖：重复权限拒绝、跨组织探测、invite 暴力尝试、异常导出、并发 finalize 冲突激增、日志敏感内容扫描、outbox DEAD、备份失败、生产管理员异常操作。

## 9. 上线安全门禁

- [ ] 威胁模型由 Security Owner 评审；
- [ ] 权限矩阵全部有正/负向 API 测试；
- [ ] 邀请、session、CSRF、return URL、限流测试通过；
- [ ] 文件上传/下载隔离和恶意样本测试通过；
- [ ] 依赖、镜像、secret、日志和 source map 扫描通过；
- [ ] 数据字段与保留清单批准；
- [ ] 飞书/AI 供应商用途和数据边界批准；
- [ ] 旧凭证、旧 DB、旧 endpoint 的阻断测试通过；
- [ ] 备份加密、恢复权限和生产发布身份验证通过；
- [ ] Sev-1/Sev-2 安全问题为 0。

## 10. 已决事项

- `DEC-006`：邀请身份 + 后续飞书绑定；
- `DEC-008`：身份/提交/评价/结果与审计 3 年，附件 1 年，通知 180 天，幂等 30 天；
- `DEC-012`：AI Advisor 不进入 P0；
- `DEC-014`：受管密钥、CI 受限身份、生产双人批准；物理配置在 G4 形成证据。
