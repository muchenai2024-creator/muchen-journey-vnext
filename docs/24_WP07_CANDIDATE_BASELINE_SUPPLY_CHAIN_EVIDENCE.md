# 24｜WP-07 候选基线与软件供应链 As-Built

状态：`AS_BUILT`  
版本：V0.2  
日期：2026-07-21  
验证环境：本地 Docker 29.6.1 / Compose 5.2.0 / Buildx 0.35、Node.js 24.16.0、PostgreSQL 18.1、Python 3.14 容器  
候选身份：`codex/wp-07-candidate-baseline` 的 clean 40 字符 `HEAD`；精确 SHA 与本地镜像 digest 写入 `artifacts/wp07-candidate/release-manifest.json`，避免在同一 Git commit 中自引用  
发布状态：`NO_GO`。本文只证明 WP-07 本地候选和供应链合同，不是受保护 main、远端 CI、registry、staging/production 或发布批准证据。

## 1. 范围、追溯与非范围

本轮只实施 WP-07，追溯到 `ISO-MUST-001/002/008`、`REQ-NFR-001/010`、`AT-ISO-001`、`AT-ARCH-005/007`。没有修改业务状态机、API 行为、数据库 schema 或 TaskVersion 内容，没有创建/派发 WP-08。

明确非范围并保持 `NOT_RUN`：push/PR、GitHub main 保护与协作者、云资源、registry push、staging/production 部署、真人 UAT、外部通知、物理 ACL 和发布签署。

## 2. 实施结果

| 缺口 | 仓库内关闭方式 |
| --- | --- |
| 无可审查 Git 基线 | 本地 `codex/wp-07-candidate-baseline` 首个候选 commit；manifest 生成前强制 full SHA + clean tree |
| 无责任人合同 | `.github/CODEOWNERS` 将默认、CI、contract、migration 与追溯矩阵归属 `@muchenai2024-creator`；远端 enforcement 待授权 |
| CI 未分层 | `.github/workflows/ci.yml` 运行 `make ci-fast`，10 分钟 timeout；`mainline.yml` 运行 `make ci-main` + `make candidate-package`；Actions 固定到 40 字符 SHA，权限仅 `contents: read` |
| 空环境路径不完整 | `ci-fast` 从 `npm ci` 开始并执行 source/legacy/secret/dependency、空库 migration、53 tests、OpenAPI、lint/type；`ci-main` 再执行持久 migration、Web production build、Compose HTTP 权限负向和 fail-closed NO_GO |
| 供应链不可绑定 | Python/Node/PostgreSQL base 使用 tag + registry digest；Gitleaks/Syft 扫描镜像使用固定 digest；API/Web/Worker 镜像写 OCI revision label |
| 无 SBOM/manifest | Syft 为三镜像生成 SPDX JSON；manifest 绑定完整 SHA、OpenAPI SHA-256、migration head、config schema、TaskVersion 工件路径/哈希/内容清单、local image content digest 与 SBOM hash |

唯一入口仍是现有 `Makefile`。WP-07 没有增加部署、发布或生产操作脚本；`scripts/wp07_candidate.py` 只负责候选元数据校验与 manifest 生成/验证，扫描工作直接使用官方工具。

## 3. Release manifest 合同

`make candidate-package` 只接受 clean 且已有 full `HEAD` 的工作树，生成：

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
- protected main、registry push 和 deploy 继续为 `NOT_RUN`。

本地 image ID 是内容摘要，但不是 registry manifest digest；后者必须在得到 push 授权并由远端 registry 返回后补证，不能伪造。

V0.2 在主任务复验后收紧 `verify`：TaskVersion 工件路径必须解析在仓库内，文件哈希和内联清单必须同时匹配；`external_status` 必须精确等于 `protected_main/registry_push/deployment = NOT_RUN`，缺键、多键或伪造 `PASS` 均 fail closed。候选 commit 不能在自身受版本控制的文档中自引用，因此最终 40 字符 SHA 仍由提交后生成并自校验的 `release-manifest.json` 和交接共同给出。

## 4. 软件供应链与安全复核

按 `security-best-practices` 完整读取并复核 Python/FastAPI、Next.js、React 与通用 Web 指导，结果：

- Gitleaks v8.30.1 对候选源码执行 redacted directory scan；仅排除 `.git` 和 Git 已忽略的 `.next`、`node_modules`、`artifacts`，并对一个明确的 WP-06 负向测试幂等字符串做单规则/单文件 allowlist；结果 0 leaks；
- `npm audit --audit-level=low` 为 0 vulnerabilities；`pip-audit==2.10.1` 对 `requirements.lock` 为 `No known vulnerabilities found`；审计工具运行在临时只读挂载容器，不加入产品依赖；
- GitHub Actions 均固定到可由官方 tag 解析的 40 字符 commit；workflow token 只有 `contents: read`；
- Python、Node、PostgreSQL、Gitleaks、Syft 镜像均固定 registry digest；API/Worker/Web 最终运行用户仍分别为非 root `journey`/`nextjs`；
- WP-07 变更未引入 `eval`、动态代码执行、`shell=True`、浏览器 HTML 注入、宽泛 CORS、客户端 secret、dev server 或 reload 生产入口；
- 新 manifest 工具只执行固定的 `git`/`docker image inspect` 参数，不接收 HTTP/业务输入；Syft 仅在候选打包步骤读取 Docker socket，固定 digest 且不进入应用运行时。
- manifest verifier 对 SBOM/TaskVersion 工件执行仓库边界、路径、哈希和内容绑定，并拒绝与当前未执行事实不完全一致的外部状态，避免被忽略工件事后篡改后继续通过。

本轮未生成仓库级 threat model、镜像 CVE hardening、日志/source map 全面扫描或 Sev-3 台账；这些属于已定义的 WP-12，不在 WP-07 提前铺开。

官方工具来源与本地核对值：

| 工具 | 固定值 | 核对来源 |
| --- | --- | --- |
| Gitleaks | v8.30.1；`sha256:c00b6b...abbb7f` | 官方 GitHub release 与 GHCR pull digest |
| Syft | v1.48.0；`sha256:b4f1df...bc405c` | 官方 GitHub release 与 Docker Hub pull digest |
| pip-audit | v2.10.1 | PyPA 官方 GitHub release；临时容器精确安装 |
| checkout/setup-node/upload-artifact | v4.2.2/v4.4.0/v4.6.2 对应 40 字符 SHA | 各官方 GitHub tag 的 `git ls-remote` |

## 5. 定向、快速与主线门禁

| 检查 | 结果 | 实测/说明 |
| --- | --- | --- |
| source/trace/migration/config | PASS | 0.08s；OpenAPI SHA-256 `5a93026e…fa566b`；head 0010；config V1 |
| secret scan | PASS | 0.78s；约 1.45 MB；0 leaks |
| WP-07 manifest tests | PASS | 9 tests；含有效基线及 external status 缺键/多键/伪造 PASS、TaskVersion 文件/内联内容篡改、路径逃逸负向；0.03s pytest / 1.02s 容器命令 |
| runtime OpenAPI equality | PASS | 非 root API 容器读取 0444 contract；1.54s |
| dependency audit | PASS | npm 0；pip 0 known；首次含 registry/漏洞库等待 103.78s |
| `make ci-fast` | PASS | 53 tests（8.28s）+ 全部快速层；107.93s，低于 10 分钟目标 |
| `make ci-main` | PASS | 53 tests（8.08s）、0009↔0010、Web production build、HTTP permission negative 与 expected `NO_GO`；182.96s |
| `make candidate-package` | 提交后生成 | 必须在 clean candidate commit 上运行；manifest 自校验结果随工件和最终交接提供 |

定向测试暴露并修复两项真实问题：首次把治理文件检查放进 API 容器测试，但镜像有意不包含 `.github`，因此将治理检查留在宿主 trace gate；其次原始 OpenAPI 文件权限为 0600，非 root 容器无法比较，改为只在镜像副本中把目录设 0555、公开合同设 0444，运行身份仍为 UID 10001。没有通过 root 运行应用或跳过检查转绿。

## 6. 耗时分段

| 阶段 | 记录 |
| --- | --- |
| preflight | 完整治理/skill/AGENTS/git/范围读取在实现计时前完成；早期未单独启动 wall-clock，作为本轮计时债务明确保留 |
| implementation + targeted | 2026-07-21T03:49:09Z 至约 04:07Z（完整门禁启动前），约 18 分钟；包含两次真实失败定位与修复 |
| bootstrap / external wait | 首次 API pinned-base/依赖构建 85.97s；首次完整 dependency audit 103.78s；下载/registry/漏洞库等待与实现分离 |
| quick gate | 107.93s |
| mainline full gate | 182.96s；PASS |
| candidate image/SBOM/manifest | 提交后单独计时并在最终交接报告 |

## 7. 工具债务、风险与退出判断

- `muchen-journey-ops` V0.2 `doctor` 对本 Greenfield 仓库返回 `Not a compatible Muchen Journey repository`；沿用 10/22 号文档记录为工具债务，未复制旧 P1 runbook 或创建第二发布路径。
- 主任务复验拒绝了 `d4bbbea728e20d2d5d1f7a0dd77f98acc1da0701`，原因是该版未绑定 `task-versions.json` 且未精确校验 `external_status`；V0.2 已加入对应 fail-closed 校验与负向测试，该 SHA 不再作为最终候选。
- 当前 Git 基线来自此前全部未跟踪的用户工作树，因此首个 commit 相对空树会显示整个仓库为新增；WP-07 特定修改清单必须与完整初始基线 stat 分开审查。
- 本地 SBOM 和 local image digest 可复现，但 GitHub workflow 尚未在远端执行；受保护 main、required checks、CODEOWNERS enforcement 与 registry digest 均无远端证据。
- 所有 staging/production、真实 UAT、物理 ACL、异机恢复和发布批准仍保持 `NOT_RUN/NO_GO`。

因此本地结论是：`LOCAL_CANDIDATE_PACKAGE_READY_FOR_MAIN_TASK_REVIEW`。在主任务完成独立复验、授权 push、建立/验证受保护 main 并取得远端 CI 结果前，WP-07 整体退出词 `CANDIDATE_BASELINE_READY` 为 **否**；不得启动 WP-08。

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

本轮不会 push、创建 PR、修改 GitHub 设置、创建云资源或部署任何环境。
