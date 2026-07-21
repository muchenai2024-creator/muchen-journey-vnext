# 15｜P0 内容、Rubric 与运营规范

状态：`APPROVED_FOR_BUILD`  
版本：V0.1  
日期：2026-07-20  
文档 Owner：Product/Content Owner + Reviewer Owner  
批准结论：P0 只交付 TSK-001“问题洞察与行动建议”，使用 Rubric V1 和两工作日 Reviewer SLA。

## 1. 目标

在开发前明确 P0 实际任务、完成标准、材料、Rubric、Reviewer 责任、SLA、版本和发布流程，让产品、数据模型、页面、API 和 UAT 围绕同一份真实内容开发。

## 2. P0 内容范围

P0 只选择能由真实新人和真实主管在试点期完成的最小任务集。任务数不是目标；完整闭环比覆盖旧探索营所有内容更重要。

G0 已批准：

| Task ID | 任务名称 | 业务目的 | 目标 Learner | 预计时长 | 交付物 | Reviewer | 是否 P0 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| TSK-001 | 问题洞察与行动建议 | 验证新人能把真实问题转化为有依据、可执行、可验证的方案 | 探索营新人 | 45–60 分钟 | 一份结构化文本提交 | 明确分配的直属主管/Reviewer | 是 |
| TSK-002 | 不进入 P0 | — | — | — | — | — | 否 |

TSK-001 V1 内容：

1. 用 100–200 字说明一个真实、具体的问题及受影响对象；
2. 提供至少两条可核对的事实或观察，区分事实与假设；
3. 给出三步以内的行动建议，写明责任人和第一步；
4. 给出一个可在两周内观察的验证指标与停止/调整条件。

如果 TSK-002 不能证明是完成同一闭环所必需，应移出 P0。

## 3. TaskVersion 内容合同

每个任务版本必须包含：

```text
stable_task_key
version
title
purpose（为什么做）
learner_outcome（完成后应理解/做到什么）
instructions（分步、可执行）
completion_criteria（可观察）
required_deliverables
allowed_attachment_types / size
reference_materials（来源、许可、有效期）
estimated_duration
rubric_version
reviewer_role/scope
feedback_sla
sensitivity/audience
published_by / reviewed_by / published_at
```

禁止把运营备注、技术字段、旧系统状态说明和未验证未来步骤放进 Learner 任务正文。

## 4. 完成标准写法

完成标准必须可观察、可提交、可评审：

- 好：提交一份包含 X、Y、Z 三项的分析，并为每项提供依据；
- 不好：深入理解业务、表现出潜力、完成探索。

每条完成标准映射一个 Rubric 维度或明确的必备检查。系统不通过关键词/文件存在自动认定能力。

## 5. Rubric 合同

每个 RubricVersion 必须包含：

| 字段 | 说明 |
| --- | --- |
| `dimension_key/title` | 稳定编号与用户可理解名称 |
| `purpose` | 该维度证明什么 |
| `evidence_expected` | Reviewer 应看哪一部分提交 |
| `levels/options` | 清晰、互斥的判断锚点 |
| `required` | 是否必须完成 |
| `feedback_prompt` | 如何给出可行动反馈 |
| `blocking_rule` | 缺失时阻断 finalize 还是允许说明 |
| `weight` | 若确需计算才使用；P0 可不做总分 |

P0 使用少量维度 + `PASS/REVISION_REQUIRED`，不把模糊总分当最终结论。未来若使用数值分数，必须通过新决策明确阈值、边界案例、校准方式和申诉/纠错。

Rubric V1 使用四个必填维度，不计算总分：

| dimension_key | 达标锚点 | 未达标时反馈要求 |
| --- | --- | --- |
| `problem_clarity` | 问题具体，受影响对象和边界清楚 | 指出仍然宽泛或缺失的对象/边界 |
| `evidence_quality` | 至少两条事实可核对，事实与假设分开 | 指出需要补充或澄清的依据 |
| `action_feasibility` | 行动不超过三步，第一步与责任人明确 | 指出不可执行或责任不清之处 |
| `validation_design` | 有两周内可观察指标及停止/调整条件 | 指出无法验证或缺少护栏之处 |

四个维度全部 `MEETS` 才能 `PASS`；任一维度 `NEEDS_WORK` 则结论必须为 `REVISION_REQUIRED`，并提供对应的可行动反馈。

## 6. Reviewer 评审协议

Reviewer 必须：

1. 确认正在评审的 Learner、TaskVersion 和 SubmissionVersion；
2. 查看全部必需交付物/附件可用性；
3. 独立填写必需 Rubric；
4. 给出具体、可执行、尊重事实的反馈；
5. 选择 PASS 或 REVISION_REQUIRED；
6. 在 finalize 前确认最终结论；
7. 不用 AI 建议替代本人判断；
8. 不覆盖旧评审，纠错走独立流程。

## 7. SLA 与升级

`DEC-016` 已批准：

| 项目 | 目标 | 超时动作 | Owner |
| --- | --- | --- | --- |
| 提交后首次评审 | 2 个工作日 | 1 个工作日提醒；超时升级给 Operator | Reviewer / Operator |
| Revision 后复评 | 2 个工作日 | 同上，队列优先级高于首次评审 | Reviewer / Operator |
| 材料缺失处理 | 1 个工作日内告知 | Learner 补充或 Operator 记录阻塞 | Reviewer / Operator |
| Reviewer 不可用 | 当日确认 | 受控重新分配并记录 reason/audit | Operator |
| 通知 DEAD | 4 小时内处理 | 运营手工联系，不改业务事实 | Operator |

系统中的“优先级”必须从批准的 SLA/等待时间/明确风险推导，不使用不可解释分数。

## 8. 内容生产与发布

```text
Draft → Content Review → Reviewer Calibration → UAT Preview
→ Approved → Published → Superseded/Withdrawn
```

- Draft 可修改；
- Published TaskVersion 不可变；
- 修改内容创建新版本，不改变在途 Assignment；
- 是否迁移在途对象由显式 Data/Product 命令决定；
- Withdrawn 阻止新分配，不抹去历史；
- 每次发布记录起草、业务审核、Reviewer 校准、敏感级别、来源与变更说明。

P0 可以用受控管理命令/配置文件发布，不必建设复杂 CMS，但不能靠手改数据库/代码常量。

## 9. 内容安全与版权

- 只向目标 audience 展示批准的材料；
- 公司/客户/个人敏感内容需要明确授权和分类；
- 外部资料记录来源、许可、可用期限和替代方案；
- 附件模板不含真实无关 PII/客户数据；
- AI 生成内容必须人工审核，不自动成为 TaskVersion/Rubric；
- 发现错误/泄密时可撤销新访问、保留历史引用并发布替代版本；
- Learner 提交的使用目的、可见角色、保留与删除符合 08 号文档。

## 10. Reviewer 校准

上线前使用至少 3 类样本（明显通过、明显需修订、边界案例）进行独立评分：

- 比较各 Reviewer 的维度选择、结论和反馈；
- 对分歧补充 Rubric 锚点，不把差异留给系统“智能解决”；
- 记录校准日期、参与人、样本版本和决定；
- 试点中监控退回率、结论分布、复评变化和支持投诉；
- Rubric 变更发布新版本，旧结论仍绑定旧版本。

## 11. UAT 内容场景

- `AT-CONTENT-001`：目标 Learner 无口头解释理解任务目标/交付物；
- `AT-CONTENT-002`：completion criteria 与 Rubric 一一对应；
- `AT-CONTENT-003`：Reviewer 用相同样本得到可解释、可校准的判断；
- `AT-CONTENT-004`：材料缺失/外链失效/附件不可读时不能误 finalize；
- `AT-CONTENT-005`：新 TaskVersion 不改变在途 Assignment；
- `AT-CONTENT-006`：撤销/替代内容后新旧对象行为清楚；
- `AT-CONTENT-007`：反馈能指向具体修改，Learner 可完成 revision；
- `AT-CONTENT-008`：敏感度、版权和 audience 审查通过。

## 12. G0/G4 完成清单

- [x] P0 Task ID、名称、目标、交付物和预计时长；
- [x] TaskVersion V1 正文与材料合同；
- [x] 完成标准和 RubricVersion；
- [x] PASS/REVISION_REQUIRED 判断规则；边界样本在 G4 真人校准；
- [x] Reviewer scope、SLA 和升级路径；真人名册在 G4 受控登记；
- [x] 构建合同已批准；Content/Reviewer/Security 真人复核在 G4 形成证据；
- [ ] Learner 5 秒/首次任务真人测试（G4，`NOT_RUN`）；
- [ ] Reviewer 真人校准记录（G4，`NOT_RUN`）；
- [x] 版本发布/撤销/替代流程；
- [x] 内容需求与 BR-003..007、API、schema、UAT 的追溯。
