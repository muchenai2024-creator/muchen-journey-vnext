# 24｜WP-07 候选基线与软件供应链 As-Built

状态：`AS_BUILT`  
版本：V0.6
日期：2026-07-21  
验证环境：本地 Docker 29.6.1 / Compose 5.2.0 / Buildx 0.35、Node.js 24.16.0、PostgreSQL 18.1、Python 3.14 容器  
候选身份：远端 `main` 的 clean 40 字符 `HEAD`；精确 SHA、镜像 digest 与外部状态写入每次 mainline run 的 `release-manifest.json`，避免在同一 Git commit 中自引用
发布状态：WP-07 `CANDIDATE_BASELINE_READY`；整体仍为 `NO_GO`。本文证明候选、远端 CI、GHCR 和受保护 `main` 闭环，不是 staging/production 或发布批准证据。

## 1. 范围、追溯与非范围

本轮只实施 WP-07，追溯到 `ISO-MUST-001/002/008`、`REQ-NFR-001/010`、`AT-ISO-001`、`AT-ARCH-005/007`。没有修改业务状态机、API 行为、数据库 schema 或 TaskVersion 内容，没有创建/派发 WP-08。

独立任务不执行 push/PR、GitHub main 保护与协作者修改、云资源或部署；主任务已按用户授权完成远端 mainline、GHCR、Public 可见性和保护规则闭环。用户在获知源码、历史、Actions、工件和外部副本不可收回风险后明确要求改为 Public。staging/production、真人 UAT、外部通知、物理 ACL 和发布签署继续非范围。

## 2. 实施结果

| 缺口 | 仓库内关闭方式 |
| --- | --- |
| 无可审查 Git 基线 | 本地 `codex/wp-07-candidate-baseline` 首个候选 commit；manifest 生成前强制 full SHA + clean tree |
| 无责任人合同 | `.github/CODEOWNERS` 将默认、CI、contract、migration 与追溯矩阵归属 `@muchenai2024-creator`；Public `main` 强制 PR 与管理员 enforcement |
| CI 未分层 | `.github/workflows/ci.yml` 运行 `make ci-fast`，10 分钟 timeout；`mainline.yml` 运行 `make ci-main` + candidate package/GHCR publish；Actions 固定到 40 字符 SHA，quick 仅 `contents: read`，mainline 最小增加 `packages: write` |
| 空环境路径不完整 | `ci-fast` 从 `npm ci` 开始并执行 source/legacy/secret/dependency、空库 migration、60 tests、OpenAPI、lint/type；`ci-main` 再执行持久 migration、Web production build、Compose HTTP 权限负向和 fail-closed NO_GO |
| 供应链不可绑定 | Python/Node/PostgreSQL base 使用 tag + registry digest；Gitleaks/Syft 扫描镜像使用固定 digest；API/Web/Worker 镜像写 OCI revision label |
| 无 SBOM/manifest | Syft 为三镜像生成 SPDX JSON；manifest 绑定完整 SHA、OpenAPI SHA-256、migration head、config schema、TaskVersion 工件路径/哈希/内容清单、local image content digest 与 SBOM hash |
| 无远端镜像回执 | mainline 仅在 `push main` 登录 GHCR，把已由 `candidate-package` 构建的三镜像分别推到 canonical package 的完整 SHA tag；对远端原始 manifest 计算 digest，并以 `repo@sha256` 二次 inspect 后才把 manifest 升级为 registry `VERIFIED` |

唯一入口仍是现有 `Makefile`。WP-07 没有增加部署、发布或生产操作脚本；`scripts/wp07_candidate.py` 只负责候选元数据校验与 manifest 生成/验证，扫描工作直接使用官方工具。

## 3. Release manifest 合同

`make candidate-package` 只接受 clean 且已有 full `HEAD` 的工作树，生成本地模式 manifest：

```text
artifacts/wp07-candidate/
├── api.spdx.json
├── web.spdx.json
├── worker.spdx.json
├── task-versions.json
└── release-manifest.json
```

manifest 至少包含：

- 40 字符 commit SHA、branch、canonical origin、build time/builder；
- `contracts/openapi.json` SHA-256；
- 唯一 migration head `0010_wp06_governance` 与 10 个 revision；
- config schema version `1`；
- `task-versions.json` 的仓库内相对路径、文件 SHA-256，以及与该工件逐项相等的 `TSK-001` V1/V2 固定 ID 和内容 SHA-256；
- API/Web/Worker local image content digest、OCI revision label、SPDX SBOM path/hash；
- local 模式要求 protected main、registry push 和 deploy 精确为 `NOT_RUN`，且三个 registry reference/digest 都为 `null`；
- registry 模式只允许 `registry_push=VERIFIED`，protected main/deployment 仍为 `NOT_RUN`；三个组件必须分别使用 `ghcr.io/muchenai2024-creator/muchen-journey-vnext-{api,web,worker}:<full-sha>` 与合法 `sha256` digest。

本地 image ID 是内容摘要，但不是 registry manifest digest；后者必须在得到 push 授权并由远端 registry 返回后补证，不能伪造。

V0.2 在主任务复验后收紧 `verify`：TaskVersion 工件路径必须解析在仓库内，文件哈希和内联清单必须同时匹配；`external_status` 必须精确等于 `protected_main/registry_push/deployment = NOT_RUN`，缺键、多键或伪造 `PASS` 均 fail closed。候选 commit 不能在自身受版本控制的文档中自引用，因此最终 40 字符 SHA 仍由提交后生成并自校验的 `release-manifest.json` 和交接共同给出。

V0.3 增加上述 local/registry 两态机。`make candidate-registry-check` 只做 canonical SHA-tag 静态校验；CI-only `candidate-registry-push` 还要求 `GITHUB_ACTIONS=true`、事件为 `push`、ref 为 `refs/heads/main` 和显式 opt-in，且只 tag/push 已存在候选镜像，不重建、不生成 `latest`。任意状态组合、组件遗漏、非 canonical repo、非法 digest 或远端 tag/digest 内容不一致均 fail closed。

V0.4 记录首个远端 mainline 证据：[run 29803354837](https://github.com/muchenai2024-creator/muchen-journey-vnext/actions/runs/29803354837) 在 SHA `166252c8172da1a64abf02cf7455d1879c680afd` 的 `make ci-main` 失败。根因一是 Ubuntu runner 没有 `rg`，旧隔离脚本在两次 `rg: not found` 后因 `if` 语义继续执行并误报通过；现改为显式选择 `rg` 或递归扩展正则 `grep`，区分“命中”“无命中”和“扫描器错误”，不可用或执行错误均 fail closed，并以无 `rg` 的 clean/forbidden/error 回归固定行为。根因二是旧 `http-negative-check` 隐式依赖本机已有 `127.0.0.1:8000` 服务；现由同一 Make target 以 `docker compose up --build -d --wait db api` 只构建/启动 DB 与 API，复用 API 既有 migrate/seed command，再执行仅负向请求的 WP-06 检查，不依赖 Worker/Web 或预运行服务。

该 run 的 candidate package、GHCR 登录、三镜像 push/远端 digest 验证和 artifact 上传步骤全部为 `skipped`，因此它没有产生任何 registry `VERIFIED` 证据；V0.4 修复仍只形成未推送的本地候选，待主任务复验新 SHA 后重新触发远端 mainline。

V0.5 记录修复后的远端证据：[run 29804468895](https://github.com/muchenai2024-creator/muchen-journey-vnext/actions/runs/29804468895) 在实现 SHA `eb4035efe2d8b08f4025e643fd53fabf3dfc0d58` 全绿，用时 5 分 26 秒；`make ci-main`、候选打包、GHCR 登录、三镜像 push、远端 immutable digest 二次验证和 artifact 上传全部成功。artifact `wp07-candidate-eb4035efe2d8b08f4025e643fd53fabf3dfc0d58` 的服务端 zip digest 为 `sha256:cc415de5…dbbea`，下载后 manifest/SBOM/TaskVersion 哈希全部复验一致；manifest 状态为 `registry_push=VERIFIED`、`protected_main=NOT_RUN`、`deployment=NOT_RUN`。

远端 digest 分别为 API `sha256:475a0a47…b1881`、Web `sha256:95e2e673…d596e`、Worker `sha256:e9e836ee…98809`，且只存在完整 SHA 标签合同，不生成 `latest`。对 `main` branch protection 的 GitHub API 复验返回 HTTP 403：Private 仓库需要升级 GitHub Pro 或改为 Public；后者违反已锁定的 Private 决策，因此未执行。该外部限制是当前唯一 WP-07 退出阻塞。

V0.6 记录用户在理解公开风险后明确批准把仓库改为 Public。可见性 API 复验为 `PUBLIC`；branch protection API 随后成功启用并回读：所有变更必须走 PR，严格要求 GitHub Actions `WP-07 / quick`，分支必须为最新且保持线性历史，合并前必须解决会话；管理员同样受规则约束，force-push 与分支删除均禁止。最初短暂把只在 `push main` 后运行的 `WP-07 / mainline` 设为 required check，经可合并性审计在任何 PR 产生前修正为 `WP-07 / quick`，避免形成永久无法合并的规则；mainline 仍在合并后执行完整门禁、GHCR push 和远端 digest 验证。

release manifest 的 `protected_main=NOT_RUN` 只表示生成该不可变工件的 workflow 没有管理 GitHub 仓库设置，不可改写为事后事实；保护规则由独立 GitHub API 回执证明。两类证据组合关闭 WP-07，不把可变设置伪装成镜像工件内部状态。

## 4. 软件供应链与安全复核

按 `security-best-practices` 完整读取并复核 Python/FastAPI、Next.js、React 与通用 Web 指导，结果：

- Gitleaks v8.30.1 对候选源码执行 redacted directory scan；仅排除 `.git` 和 Git 已忽略的 `.next`、`node_modules`、`artifacts`，并对一个明确的 WP-06 负向测试幂等字符串做单规则/单文件 allowlist；结果 0 leaks；
- `npm audit --audit-level=low` 为 0 vulnerabilities；`pip-audit==2.10.1` 对 `requirements.lock` 为 `No known vulnerabilities found`；审计工具运行在临时只读挂载容器，不加入产品依赖；
- GitHub Actions 均固定到可由官方 tag 解析的 40 字符 commit；quick token 只有 `contents: read`，mainline 为 GHCR 增加唯一必要的 `packages: write`；
- Python、Node、PostgreSQL、Gitleaks、Syft 镜像均固定 registry digest；API/Worker/Web 最终运行用户仍分别为非 root `journey`/`nextjs`；
- WP-07 变更未引入 `eval`、动态代码执行、`shell=True`、浏览器 HTML 注入、宽泛 CORS、客户端 secret、dev server 或 reload 生产入口；
- 新 manifest 工具只执行固定的 `git`/`docker image inspect` 参数，不接收 HTTP/业务输入；Syft 仅在候选打包步骤读取 Docker socket，固定 digest 且不进入应用运行时。
- manifest verifier 对 SBOM/TaskVersion 工件执行仓库边界、路径、哈希和内容绑定，并拒绝与当前未执行事实不完全一致的外部状态，避免被忽略工件事后篡改后继续通过。
- mainline token 权限仅 `contents: read` + `packages: write`；GHCR 登录使用官方 `docker/login-action` v4.1.0 的 40 字符 commit 与 `${{ secrets.GITHUB_TOKEN }}`，登录位于完整本地门禁和候选构建之后。token 不写文件、不进入命令参数或工件。
- registry digest 只来自 `docker buildx imagetools inspect --raw` 的远端 manifest 字节，并由 immutable `repo@sha256` 再取一次验证；local image ID/RepoDigest 不参与远端 `VERIFIED` 判定。

本轮未生成仓库级 threat model、镜像 CVE hardening、日志/source map 全面扫描或 Sev-3 台账；这些属于已定义的 WP-12，不在 WP-07 提前铺开。

官方工具来源与本地核对值：

| 工具 | 固定值 | 核对来源 |
| --- | --- | --- |
| Gitleaks | v8.30.1；`sha256:c00b6b...abbb7f` | 官方 GitHub release 与 GHCR pull digest |
| Syft | v1.48.0；`sha256:b4f1df...bc405c` | 官方 GitHub release 与 Docker Hub pull digest |
| pip-audit | v2.10.1 | PyPA 官方 GitHub release；临时容器精确安装 |
| checkout/setup-node/upload-artifact | v4.2.2/v4.4.0/v4.6.2 对应 40 字符 SHA | 各官方 GitHub tag 的 `git ls-remote` |
| docker/login-action | v4.1.0；`4907a6ddec9925e35a0a9e82d7399ccc52663121` | Docker 官方 immutable release/tag |

## 5. 定向、快速与主线门禁

| 检查 | 结果 | 实测/说明 |
| --- | --- | --- |
| source/trace/migration/config | PASS | 0.08s；OpenAPI SHA-256 `5a93026e…fa566b`；head 0010；config V1 |
| secret scan | PASS | 0.78s；约 1.45 MB；0 leaks |
| WP-07 manifest tests | PASS | 25 tests；含 local/registry 正态及升级、状态与组件精确集合、canonical repo/禁止 latest、digest/遗漏/伪造、TaskVersion 篡改/路径逃逸、远端 immutable 二次验证；0.07s pytest / 1.30s 容器命令 |
| CI portability regression | PASS | 3 tests；PATH 无 `rg` 时 clean tree 通过、forbidden reference 失败，扫描器错误/缺失 fail closed；HTTP target 静态合同精确限定 `db api` |
| GHCR dry-run/static | PASS | 三个 canonical package + 完整 SHA tag；`registry_push=NOT_RUN`；workflow YAML 与全部 action 40 字符 SHA 合同通过；无登录/push |
| runtime OpenAPI equality | PASS | 非 root API 容器读取 0444 contract；1.54s |
| dependency audit | PASS | npm 0；pip 0 known；首次含 registry/漏洞库等待 103.78s |
| `make ci-fast` | PASS | V0.4 最终套件 79 tests + 全部快速层；本地 120.39s，低于 10 分钟目标 |
| `make ci-main` | PASS | 79 tests、0009↔0010、Web production build、自举式 HTTP permission negative 与 expected `NO_GO`；本地 137.80s，远端 run 29804468895 PASS |
| `make candidate-package` | PASS | 最终实现 SHA 本地 154.72s；远端重建、三份 SPDX SBOM、registry manifest 与 artifact 上传全部 PASS |
| GHCR remote evidence | PASS | API `475a0a47…`、Web `95e2e673…`、Worker `e9e836ee…`；远端 immutable digest 二次 inspect 与下载工件哈希一致 |

定向测试暴露并修复两项真实问题：首次把治理文件检查放进 API 容器测试，但镜像有意不包含 `.github`，因此将治理检查留在宿主 trace gate；其次原始 OpenAPI 文件权限为 0600，非 root 容器无法比较，改为只在镜像副本中把目录设 0555、公开合同设 0444，运行身份仍为 UID 10001。没有通过 root 运行应用或跳过检查转绿。

## 6. 耗时分段

| 阶段 | 记录 |
| --- | --- |
| preflight | 完整治理/skill/AGENTS/git/范围读取在实现计时前完成；早期未单独启动 wall-clock，作为本轮计时债务明确保留 |
| implementation + targeted | 2026-07-21T03:49:09Z 至约 04:07Z（完整门禁启动前），约 18 分钟；包含两次真实失败定位与修复 |
| bootstrap / external wait | 首次 API pinned-base/依赖构建 85.97s；首次完整 dependency audit 103.78s；下载/registry/漏洞库等待与实现分离 |
| quick gate | V0.1 107.93s；V0.2 复验修复后 123.04s |
| mainline full gate | 182.96s；PASS |
| candidate image/SBOM/manifest | 提交后单独计时并在最终交接报告 |

## 7. 工具债务、风险与退出判断

- `muchen-journey-ops` V0.2 `doctor` 对本 Greenfield 仓库返回 `Not a compatible Muchen Journey repository`；沿用 10/22 号文档记录为工具债务，未复制旧 P1 runbook 或创建第二发布路径。
- 主任务复验拒绝了 `d4bbbea728e20d2d5d1f7a0dd77f98acc1da0701`，原因是该版未绑定 `task-versions.json` 且未精确校验 `external_status`；V0.2 已加入对应 fail-closed 校验与负向测试，该 SHA 不再作为最终候选。
- 当前 Git 基线来自此前全部未跟踪的用户工作树，因此首个 commit 相对空树会显示整个仓库为新增；WP-07 特定修改清单必须与完整初始基线 stat 分开审查。
- GitHub workflow 与 GHCR registry-mode manifest 已有远端 `VERIFIED` 证据；个人 `gh` token 没有 `read:packages` scope，主任务没有扩大授权，而是用 Actions push/immutable-inspect 日志和下载工件交叉复验。
- 仓库现为 Public，历史、Actions 日志与现存工件对所有人可见；该风险由用户明确接受。未来改回 Private 不能收回既有外部 clone/fork，且必须作为独立治理变更处理。
- branch protection 已由 API 回读验证；required check 使用 PR 可实际触发的 `WP-07 / quick`，而不是合并后才触发的 mainline。管理员 enforcement、线性历史、会话解决、禁止 force-push/删除均开启。
- GitHub 对当前 checkout/setup-node/upload-artifact 固定版本给出 Node.js 20 deprecated、强制 Node 24 的维护注记；本次运行成功，后续需在不放松 40 字符 action pin 的前提下升级固定版本。
- 所有 staging/production、真实 UAT、物理 ACL、异机恢复和发布批准仍保持 `NOT_RUN/NO_GO`。

因此当前结论是：`CANDIDATE_BASELINE_READY`。远端 CI/GHCR 与独立 branch-protection API 证据已关闭 WP-07；可按单一 WIP 启动 WP-08。staging、真实身份/集成、UAT、试点和生产仍为 `NOT_RUN/NO_GO`。

## 8. 关键文件

- `.github/CODEOWNERS`
- `.github/workflows/ci.yml`
- `.github/workflows/mainline.yml`
- `.gitleaks.toml`
- `Makefile`
- `scripts/wp07_candidate.py`
- `tests/test_wp07_candidate.py`
- `apps/api/Dockerfile`
- `apps/worker/Dockerfile`
- `apps/web/Dockerfile`
- `compose.yaml`
- `docs/13_REQUIREMENTS_TRACEABILITY_MATRIX.md`

独立任务没有 push、创建 PR、修改 GitHub 设置、创建云资源或部署环境；Public 可见性与保护规则由主任务按用户明确授权完成并复验，未购买套餐或执行部署。
