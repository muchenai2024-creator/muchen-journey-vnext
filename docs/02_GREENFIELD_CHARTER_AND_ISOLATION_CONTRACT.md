# 02｜Greenfield 项目章程与隔离合同

状态：`APPROVED_FOR_BUILD`  
版本：V0.1  
日期：2026-07-20  
文档 Owner：Product Owner + Tech Lead  
一票否决：任一 `ISO-MUST` 不满足，项目不得称为 Greenfield，也不得进入 G1。

## 1. 项目使命

从零开发一个独立的 Muchen Journey vNext，以最小而完整的真实用户闭环验证产品价值。新系统以清晰的领域模型、单一事实源和可验证质量为基础，不继承旧系统的代码结构、兼容路由、状态别名、数据表设计、发布脚本或历史补丁。

## 2. “独立”的可测试定义

新系统只有同时满足以下条件才算独立：

| ID | 隔离维度 | 强制合同 | 证明方式 |
| --- | --- | --- | --- |
| ISO-MUST-001 | 源码 | 独立 Git 仓库；无旧仓库 submodule、workspace、包、复制目录或构建引用 | 在构建机完全不挂载旧仓库仍能 build/test |
| ISO-MUST-002 | 依赖 | 依赖只来自公开包仓库或 vNext 自有包；禁止引用旧应用内部模块 | lockfile + import/dependency scan |
| ISO-MUST-003 | 数据库 | 独立 PostgreSQL 实例/数据库/角色；新迁移从 `0001` 开始；账号无旧库权限 | 网络与数据库 ACL 测试；旧库下线时全流程通过 |
| ISO-MUST-004 | 运行时 | 禁止调用旧 API、读取旧对象存储、旧缓存、旧队列或旧飞书多维表格作为事实源 | egress allowlist；旧端点不可达的集成测试 |
| ISO-MUST-005 | 身份 | vNext 拥有内部 `user_id` 和身份映射；外部身份只是映射，不复用旧会话/token | 新旧 cookie 互不接受；独立 session secret |
| ISO-MUST-006 | 路由 | vNext 只有 canonical 路由；代码中不存在 legacy redirect/V1/V2 产品路径 | route manifest scan；未知旧路径返回 404/410 |
| ISO-MUST-007 | 环境 | dev/test/staging/prod 均为 vNext 独立配置、域名、密钥与资源命名空间 | 环境清单和资源标签审计 |
| ISO-MUST-008 | 部署 | 独立 CI/CD、镜像仓库、运行目标、健康检查和回滚记录 | 从空环境独立部署演练 |
| ISO-MUST-009 | 可观测 | 独立日志、告警、Sentry/APM 项目和发布 revision | 告警演练；无旧服务日志混入 |
| ISO-MUST-010 | 回滚 | 只能回滚到上一 vNext 兼容版本或维护模式；不得恢复旧系统业务写入 | 发布演练与运行手册审计 |
| ISO-MUST-011 | 数据导入 | 历史数据通过离线、版本化、可重复的一次性导入包进入；导入器不连接旧生产库 | 导入工件校验和；目标库重放一致 |
| ISO-MUST-012 | 旧系统 | 旧系统是只读参考/归档；不能作为 vNext 降级路径或在线依赖 | 断开旧系统后 vNext UAT 全通过 |

## 3. 允许与禁止的继承

### 3.1 可以继承

- 经 Product Owner 重新确认的用户问题、术语和业务规则；
- 经 Data Owner 识别的合法历史事实；
- 经 QA 复现并转写为 `AT-*` 的真实用户场景；
- 经安全评审后继续使用的公开技术标准或第三方服务；
- 通过 ADR 重新选择的同类技术栈，例如 Next.js、FastAPI、PostgreSQL；选择相同技术不等于复用旧代码。

### 3.2 禁止继承

- 旧前后端源码、组件、适配器、route registry、page contract registry；
- 旧数据库模型、表名、枚举、Alembic 迁移链和 seed；
- 旧 V1/V2/P0/P1 命名、兼容映射和 feature flag；
- 旧 session、cookie、JWT secret、API key 和 `.env`；
- 旧部署、备份、恢复、验收与 release gate 脚本；
- 旧 mock 作为生产 fallback；
- 旧多维表格、localStorage、JSON 投影作为业务权威；
- 为让旧页面继续工作而增加的 redirect、adapter、bridge、双读或双写。

如确需复用某段旧代码，必须先把 `DEC-001` 从“Greenfield”改为其他项目类型，并重新评估本合同。不能以“只复用一个稳定组件”为名打开例外。

## 4. 初始产品边界

批准的首版只完成“探索营真实闭环”：

```text
受邀/登记 → 身份确认 → 当前任务 → 提交 → 主管评审
→ 需要修订或通过 → 结果与下一步/交接
```

首版不建设平台化多空间，不同时开发新手村、AI 学院、Talent OS、完整公会、积分商城、虚拟人或 AIGC 内容系统。未来扩展通过稳定领域接口进入，而不是预先创建空框架或复制旧空间。

该范围已由 `DEC-004` 批准。

## 5. 新系统命名原则

- 用户界面和路由不出现 `V2`、`P0`、`legacy` 或 `new`；版本是交付信息，不是产品概念。
- API 使用标准版本前缀，例如 `/api/v1`；它表示兼容协议版本，不表示旧系统旁路。
- 数据库从 `0001_initial` 开始，不承接旧编号。
- 环境资源使用明确前缀，例如 `journey-next-*`，最终命名由 `DEC-003` 确认。
- 代码模块按领域命名：identity、enrollment、assignment、submission、review、result、notification、audit。

## 6. 独立性验收场景

### AT-ISO-001｜无旧源码构建

在一个只包含 vNext 仓库和公开依赖缓存的空白 runner 中执行依赖安装、类型检查、单测和生产构建。旧项目路径不存在。结果必须通过。

### AT-ISO-002｜旧服务断网运行

运行环境只允许访问 vNext 数据库、vNext 对象存储和已批准第三方域名；明确拒绝旧 API、旧数据库、旧对象存储和多维表格数据端点。完整 UAT 必须通过。

### AT-ISO-003｜新旧凭证互斥

旧 session/cookie/token 请求 vNext 必须被拒绝；vNext 凭证请求旧系统不应获得额外权限。错误不得触发兼容登录桥。

### AT-ISO-004｜无兼容路由

已知旧路径清单在 vNext 应返回 404/410 或由外部网关跳转到公开说明页；vNext 应用内部不得存在旧页面实现或状态转换。

### AT-ISO-005｜全新数据库重建

从空 PostgreSQL 执行 vNext 迁移，创建完整 P0 schema，加载最小 seed，运行闭环。迁移日志只包含 vNext `0001+`。

### AT-ISO-006｜离线导入

把固定版本的中性导出包放入隔离环境，在无法访问旧系统的情况下导入两次：第一次产生目标记录，第二次安全重放且不重复。拒绝记录进入隔离报告，不自动猜测。

### AT-ISO-007｜vNext 内部回滚

部署 vNext N，再部署 N+1 并模拟失败；回滚到 N 或维护模式，保留已经提交的新事实。旧系统保持只读且不接管写入。

## 7. 物理资源清单

G0 必须把以下占位符替换成真实值：

| 资源 | Dev | Test | Staging | Prod | Owner |
| --- | --- | --- | --- | --- | --- |
| Git 仓库 | `muchen-journey-vnext` | 同左 | 同左 | 同左 | Liu Mowen |
| 应用域名 | `localhost:3000` | `APP_ORIGIN` 的 test 独立值 | `APP_ORIGIN` 的 staging 独立值 | `APP_ORIGIN` 的 prod 独立值 | Liu Mowen；物理值 G4 验证 |
| PostgreSQL | `journey_next_dev` | `journey_next_test` | `journey_next_staging` | `journey_next_prod` | Liu Mowen |
| 对象存储 bucket | `journey-next-dev-attachments` | `journey-next-test-attachments` | `journey-next-staging-attachments` | `journey-next-prod-attachments` | Liu Mowen |
| 身份应用/回调 | `journey-next-dev` | `journey-next-test` | `journey-next-staging` | `journey-next-prod` | Liu Mowen；物理值 G4 验证 |
| CI/CD | local Make + GitHub Actions | GitHub Actions | GitHub Actions staging environment | GitHub Actions production environment | Liu Mowen |
| 镜像仓库 | local image | `journey-next-test-*` | `journey-next-staging-*` | `journey-next-prod-*` | Liu Mowen；provider G4 验证 |
| 日志/APM/Sentry | structured stdout | `journey-next-test` | `journey-next-staging` | `journey-next-prod` | Liu Mowen；provider G4 验证 |
| 密钥管理 | 本地未提交 `.env` | CI secret store | staging secret store | managed production secret store | Liu Mowen |
| 备份目的地 | 本地隔离测试卷 | test 隔离卷 | staging 异机对象存储 | prod 加密异机对象存储 | Liu Mowen；恢复证据 G4 验证 |

## 8. 边界变更程序

任何会连接旧系统、复用旧代码、共享旧数据库、共享旧凭证或恢复旧写入的提案都属于项目类型变更，必须：

1. 新建 ADR 和 `DEC-*`；
2. 明确 Greenfield 目标是否被放弃；
3. 重新评估全部 `ISO-MUST`；
4. 获得 Product、Tech、Data、Security、QA、Ops 一致批准；
5. 在批准前保持 No-Go。

## 9. 签署

| 责任 | 姓名 | 结论 | 日期 |
| --- | --- | --- | --- |
| Product Owner | Liu Mowen | BUILD GO | 2026-07-20 |
| Tech Lead | Liu Mowen | BUILD GO | 2026-07-20 |
| Data Owner | Liu Mowen | BUILD GO | 2026-07-20 |
| Security Owner | Liu Mowen | BUILD GO；release evidence NOT_RUN | 2026-07-20 |
| QA Owner | Liu Mowen | BUILD GO；human UAT NOT_RUN | 2026-07-20 |
| Ops Owner | Liu Mowen | BUILD GO；production verification NOT_RUN | 2026-07-20 |
