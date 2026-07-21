# 25｜WP-08 Definition of Ready As-Built

状态：`AS_BUILT`

版本：V0.1

日期：2026-07-21

验证环境：macOS / Docker 29.6.1 / Compose 5.2.0 / Node.js 24.16.0 / Python 3.14 容器 / Chromium 1232

发布状态：仅完成 WP-08 的 provider-neutral Definition of Ready；物理 staging、真实域名/TLS、托管 DB/对象存储/secret、CI deploy identity 与 ACL 仍为 `NOT_RUN`，整体发布为 `NO_GO`。

## 1. 范围与授权边界

本轮以受保护 `origin/main` 的完整 SHA `060dbe388e4c446191d64bb28387705c8960df21` 为 base，只建立一个 `codex/wp-08-preflight-harness` WIP。实施范围是 23 号文档的六项 P0 开工检查，不创建云资源、GitHub Environment、域名、证书、secret、网络 ACL 或 staging deployment，不选择需要采购或承诺成本的供应商。

本轮对 `ISO-MUST-003/004/007/008/009/012`、`DEC-003/013/014`、`AT-ISO-002/003/005` 和 `AT-ARCH-002/003/005` 只关闭工程前置，不声称物理验收通过。真实 staging 仍须在明确平台、region、资源 Owner 和外部写入授权后执行。

## 2. 六项 P0 证据

| 开工项 | 结果 | 可复现证据 |
| --- | --- | --- |
| Git/PR | 待 PR 创建后最终勾选 | base SHA 已固定；单一分支；`make wp08-git-check` 要求 clean tree、`codex/wp-08-*` 且 `merge-base == origin/main`，任一漂移 fail closed |
| 浏览器预检 | PASS | `make browser-preflight/browser-smoke`；固定 Chromium 1232、`config/wp08_browser_smoke.json`、`output/playwright/wp08`；1440×900、768×1024、390×844 三视口均无 overflow，38 个 focusable，Tab focus 成功，console 0 error/0 warning |
| migration / fixture | PASS | 静态检查拒绝重复及超过 Alembic `varchar(32)` 的 revision，root=`0001_initial`、唯一 head=`0010_wp06_governance`；空库 86 tests；持久库 `0009→0010→0009→0010` 保真；manifest 由唯一 `python -m journey_api.seed` builder 生成并只列 synthetic stable references/表/字段 |
| 停止态自举/工具 | PASS | 项目服务停止时 `make wp08-cold-preflight` 验证 Docker/Compose/git/Python/Node/npm/npx 和 compose config；浏览器 smoke 自行启动 DB/API/Web 并结束后停止；本地端口只绑定 loopback 且门禁使用显式隔离端口 |
| Ops V0.3+ | PASS（边界保持） | `doctor`: `OPS_DOCTOR=PASS`、profile=`greenfield-vnext`、missing tools/files/targets=`none`；`status/gates` 原样报告 dirty 开发分支、stale local candidate、8 项外部 `NOT_RUN`、`NO_GO`，且 `production_mutation_executed=false` |
| Public/私有证据 | PASS | `evidence/private/wp08` 被 Public Git ignore；目录 `0700`、`boundary.json` `0600`，Owner=本地仓库 Owner、访问范围=`LOCAL_FILESYSTEM_OWNER_ONLY`、保留期 90 天、公开引用格式 `PEV-WP08-YYYYMMDD-<NON_SECRET_ID>`；gitleaks 0 leak |

浏览器截图、CLI config、真实本机路径和 WP-06 运行报告均只在受控本地证据目录，不进入 Public Git。Public 文档只保留检查结果、不可逆/非敏感标识与私有证据引用规则。

## 3. 实施合同

- `scripts/wp08_readiness.py` 是只读或本地私有证据写入的 fail-closed readiness 工具；它没有 deploy 子命令。
- `browser-preflight` 要求显式 `PLAYWRIGHT_CLI`、固定 Chromium executable、`BROWSER_BASE_URL` 和 local/staging scope。staging scope 只接受非 localhost 的 HTTPS URL。
- `browser-smoke` 复用 Playwright CLI，不增加 `@playwright/test` 或第二套浏览器框架；本地模式从停机状态启动并停止现有 Compose 服务。
- `compose.yaml` 的 DB/API/Web host port 改为 `127.0.0.1` 且允许显式覆盖；WP-08 门禁默认使用 DB `35432`、API `38000`，避免依赖常见宿主端口。
- `scripts/wp07_candidate.py` 的既有 migration source-of-truth 增加 revision 长度与重复 ID 拒绝；没有复制第二套 migration parser。
- `scripts/wp06_ops.py` 的 HTTP 负向门禁接受并校验显式 `MJ_API_PORT`，仍只访问 loopback、只运行既有负向权限请求。
- API candidate image 包含已受版本控制的 `config` 合同，使容器内测试与宿主使用同一 browser spec；应用仍以非 root 用户运行。

## 4. 失败记录与改进

首次 browser smoke 和首次持久 migration check 都在启动前因宿主已有其他 PostgreSQL 占用 `5432` 而失败；容器没有完成启动，迁移没有执行，失败未计为 PASS。修复不是停止其他项目，而是把本仓库 host port 限制在 loopback、支持显式覆盖，并给门禁使用隔离端口；随后两条路径均通过。

完整 `make ci-fast` 的 `pip-audit` 漏洞索引查询等待约 7 分钟，但最终返回 `No known vulnerabilities found`，没有跳过安全门禁。该外部等待与代码执行耗时分开记录，后续可为审计网络调用增加受评审的超时/重试策略，不能用缓存或忽略错误伪造绿灯。

## 5. 验证结果

| 检查 | 结果 |
| --- | --- |
| WP-07/WP-08 定向测试 | 37 passed；含 migration、evidence symlink/权限、browser URL/scope、显式 API port 负向 |
| `make ci-fast` | PASS；86 passed，OpenAPI equality、ESLint、TypeScript、isolation、secret 与 dependency audit 全通过 |
| 空库 migration | PASS；`0001→0010` 后 seed 与 86 tests |
| 持久 migration | PASS；`0009↔0010` 升降级与业务事实保真 |
| HTTP permission negative | PASS；DB/API 自举到隔离 loopback 端口，未执行成功业务 mutation |
| browser smoke | PASS；三视口、console、overflow、focus/keyboard |
| release gate | 预期 `NO_GO`；8 项真人/外部/物理门禁保持 `NOT_RUN` |

## 6. 当前阻塞与下一 Owner 动作

WP-08 物理实现尚缺以下执行输入：staging 平台与 region、staging 域名/证书 Owner、托管 PostgreSQL、S3-compatible storage、secret/KMS、日志/APM 供应商、CI deploy identity，以及这些资源的成本与外部写入授权。没有这些输入时不得选择供应商或创建资源。

因此本文当前退出词不是 `STAGING_ISOLATION_VERIFIED`，而是 `WP08_DEFINITION_OF_READY`。完成 PR/required check 后可关闭六项开工检查；随后唯一下一动作是由环境 Owner 给出上述精确 staging 资源选择与写入授权，再继续 WP-08，而不是越过它启动 WP-09。
