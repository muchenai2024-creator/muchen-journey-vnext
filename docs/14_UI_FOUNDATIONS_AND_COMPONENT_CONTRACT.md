# 14｜UI Foundations 与正式组件合同

状态：`APPROVED_FOR_BUILD`  
版本：V0.1  
日期：2026-07-20  
文档 Owner：Design Owner + Frontend Owner  
批准基线：`DEC-015` 已批准；P0 使用系统字体、蓝色主操作、4px 网格、WCAG 2.2 AA 和下列固定 token。

## 1. 目标

建立一套服务于“当前行动、清晰反馈、可信状态”的正式 UI 语言。P0 不从旧系统复制样式、Tailwind class、组件、页面壳或游戏化装饰，也不为多个未来空间预建主题系统。

## 2. 设计原则

- 清晰优先：层级帮助用户完成当前任务，不用装饰制造复杂度；
- 一致语义：相同状态、动作和风险始终使用相同语言和视觉；
- 行动优先：主 CTA、当前状态、错误恢复和焦点最醒目；
- 内容优先：任务正文、提交和反馈有舒适阅读宽度；
- 克制游戏化：进度与完成反馈可以有成就感，但不让后台/评审变成游戏皮肤；
- 可访问默认：键盘、对比度、缩放、焦点和错误不是后补项；
- 一个正式组件：同一行为不按 Learner/Reviewer/Operator 复制三套。

## 3. Token 基线

以下值是 P0 构建基线；变更必须更新 `DEC-015`，不得由页面自行覆盖。

### 3.1 字体与字号

- 字体：`ui-sans-serif, -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif`；
- 正文基准：16px；辅助文本不低于 14px；
- 标题建议：20/24/32px 三级，不建立过长梯度；
- 行高：正文约 1.5–1.7，表单/按钮保证文字不裁切；
- 代码/request id 使用等宽字体但不缩小到难读。

### 3.2 间距与布局

- 4px 基础网格；常用间距 4/8/12/16/24/32/48；
- 内容阅读宽度建议 640–760px；工作台可使用更宽双栏但保持主操作清楚；
- 390px 单栏；768px 根据内容采用单栏/主次栏；1280px Reviewer/Operator 可双栏；
- 固定 header/footer 不得遮挡主操作或错误；
- 卡片/容器用于分组，不把每段文字装进卡片。

### 3.3 形状与层级

- 圆角建议 8/12px 两级；
- 阴影仅表达浮层/层级，不作为默认卡片装饰；
- 边框、背景、留白优先于大量阴影；
- 动画 150–250ms，尊重 `prefers-reduced-motion`；业务成功不依赖动画完成。

### 3.4 颜色语义

正式色值如下，均需在组件测试中验证 AA 对比度：

| Token | 用途 | 禁止 |
| --- | --- | --- |
| `surface/base/raised` | `#F6F7FB / #FFFFFF / #FFFFFF` | 每页自定义背景 |
| `text/primary/secondary/muted/inverse` | `#172033 / #465168 / #667085 / #FFFFFF` | 用低对比度表达正文 |
| `action/primary/hover/pressed/disabled` | `#2854D7 / #1F46BD / #183A9E / #AAB7D8` | 不同空间不同主色语义 |
| `status/info/success/warning/error` | `#2457D6 / #18794E / #9A6700 / #B42318` | 单靠颜色传达状态 |
| `border/default/strong/focus` | `#D8DDE8 / #98A2B3 / #2854D7` | 移除键盘焦点 |

正常正文/控件、焦点和大文本对比度至少满足批准的 AA 目标；目标建议采用 WCAG 2.2 AA。

## 4. 正式组件清单

### 基础

- `Button`：primary/secondary/tertiary/destructive/link；loading 仍保留可识别文本；
- `Link`：内部/外部语义明确；
- `TextField`、`TextArea`、`Select/Radio/Checkbox`：label、description、error、required；
- `FileUpload`：选择、进度、READY、失败、删除、重传；
- `Dialog`、`Disclosure`、`Menu`：完整焦点/键盘合同；
- `StatusBadge`：只显示简短状态，不能成为主行动；
- `Banner/InlineAlert`：info/success/warning/error 与恢复动作；
- `Skeleton/Empty/ErrorState`：不制造假业务状态。

### 领域

- `CurrentActionCard`：当前问题、原因、责任人/反馈预期、唯一 CTA；
- `TaskBrief`：目标、完成标准、材料、版本；
- `SubmissionComposer`：草稿、附件、校验、提交/冲突恢复；
- `SubmissionHistory`：只读版本时间线；
- `ReviewQueueItem`：身份、等待时长、优先原因、材料完整性；
- `ReviewEvidenceView`：固定提交版本和附件；
- `RubricForm`：必填项、评分/结论、字段错误、唯一 finalize；
- `OutcomeSummary`：人工结论、核心反馈、下一步；
- `AsyncDeliveryStatus`：通知/AI 状态，明确不等于业务状态；
- `AuditSummary`：最小事件摘要和 request id。

P0 不建设 SpaceShell、RouteRegistry UI、通用 Dashboard Builder、主题商城或动态组件运行时。

## 5. 组件状态合同

每个可交互组件在实现前必须有：

- default、hover、focus-visible、active、disabled；
- loading、success、validation error、server error；
- 权限拒绝/只读（如适用）；
- 长文案、中英文/数字、空值；
- 200% 文本缩放；
- 390/768/1280；
- 键盘与屏幕阅读器名称/关系。

禁用状态必须说明原因时使用相邻文本/提示；不能让用户猜测。

## 6. 页面组合规则

- 一页最多一个 primary Button 对应核心业务命令；
- StatusBadge 不代替清晰的状态说明；
- Banner 只承载跨页面/高优先问题，字段错误就近显示；
- CurrentActionCard 不与另一个“大号推荐卡”竞争；
- Reviewer 双栏中队列和详情保持选择/焦点关系；
- 历史默认次级，不让旧版本与当前版本同等突出；
- destructive Dialog 显示对象、影响和不可逆性，要求 reason 时就地填写。

## 7. 内容与语气

- 使用用户语言：“等待主管反馈”，不显示 `IN_REVIEW`；
- 说明责任与下一步：“张三将在…前反馈”，避免“系统处理中”；
- 错误说明发生什么、是否保存、怎么办和 request id；
- AI 明确写“AI 建议”，人工结论写 Reviewer 与时间；
- 不用“宝藏/副本/通关”等词掩盖业务交付和评审；若品牌决定保留游戏化词汇，必须同时保持业务含义清楚；
- 按钮使用动作动词，不用“确定/处理/下一步”泛化所有场景。

## 8. 交付与验收

G0/G1 交付：

- [ ] Token 表（最终色值、字体、字号、间距、圆角、阴影、动效、断点）；
- [ ] 基础/领域组件状态图；
- [ ] 04 号文档所有页面状态原型；
- [ ] 组件可访问性清单；
- [ ] 品牌资产来源/许可；
- [ ] 实现与视觉回归方式（建议组件预览 + 少量页面截图，不建立巨型全站快照）。

验收：

- `AT-UI-001`：Token 无页面级未解释漂移；
- `AT-UI-002`：同一业务行为只使用一个正式组件；
- `AT-UI-003`：组件状态完整且键盘/焦点通过；
- `AT-UI-004`：颜色对比、200% 缩放、reduced motion 通过；
- `AT-UI-005`：三视口页面无动作丢失/遮挡；
- `AT-UI-006`：旧组件/样式/游戏皮肤未复制进入新仓库。
