import { assignEnrollmentReviewer, cancelEnrollment } from "@/app/actions";
import {
  apiRequest,
  OpsAuditEntry,
  OpsEnrollment,
  OpsTaskDefinition,
  RuntimeStatus,
} from "@/lib/server/api";

export const dynamic = "force-dynamic";

function formatTime(value: string | null): string {
  if (!value) return "尚无心跳";
  return new Intl.DateTimeFormat("zh-CN", {
    dateStyle: "medium",
    timeStyle: "medium",
  }).format(new Date(value));
}

export default async function OpsPage({
  searchParams,
}: {
  searchParams: Promise<{ updated?: string }>;
}) {
  const [query, tasks, enrollments, audit, runtime] = await Promise.all([
    searchParams,
    apiRequest<{ items: OpsTaskDefinition[] }>("/api/v1/ops/task-definitions", "OPERATOR"),
    apiRequest<{ items: OpsEnrollment[] }>("/api/v1/ops/enrollments", "OPERATOR"),
    apiRequest<{ items: OpsAuditEntry[] }>("/api/v1/ops/audit?limit=20", "OPERATOR"),
    apiRequest<RuntimeStatus>("/api/v1/ops/runtime-status", "OPERATOR"),
  ]);

  return (
    <section className="ops-page">
      <p className="eyebrow">Operator · local/test only</p>
      <h1>受控运营与运行状态</h1>
      <p className="lede">
        这里没有通用状态编辑器。所有写入都绑定组织、对象、角色、expected revision、幂等键与理由。
      </p>
      <p className="notice">
        当前仅为本地候选：真人 UAT、真实通知、staging/production、物理 ACL、异机恢复与发布签署均为 NOT_RUN，发布判定必须 NO_GO。
      </p>
      {query.updated ? <p className="success-text" role="status">受控命令已写入并记录审计。</p> : null}

      <section className="panel ops-section" aria-labelledby="runtime-heading">
        <div className="section-heading-row">
          <div>
            <p className="section-label">REVISION / HEALTH / WORKER / OBSERVABILITY</p>
            <h2 id="runtime-heading">运行快照</h2>
          </div>
          <span className={`material-status ${runtime.worker.stale ? "incomplete" : "complete"}`}>
            Worker {runtime.worker.status}
          </span>
        </div>
        <dl className="ops-facts">
          <div><dt>Release</dt><dd>{runtime.release}</dd></div>
          <div><dt>Migration</dt><dd>{runtime.migration_revision}</dd></div>
          <div><dt>Config schema</dt><dd>V{runtime.config_schema_version}</dd></div>
          <div><dt>API / DB</dt><dd>{runtime.api.status} / {runtime.database.status}</dd></div>
          <div><dt>Worker revision</dt><dd>{runtime.worker.release ?? "未知"}</dd></div>
          <div><dt>Worker heartbeat</dt><dd>{formatTime(runtime.worker.last_seen_at)}</dd></div>
          <div><dt>Outbox / dead</dt><dd>{runtime.metrics.outbox_backlog} / {runtime.metrics.notification_dead}</dd></div>
          <div><dt>Observability</dt><dd>{runtime.observability_mode} · external=false</dd></div>
        </dl>
      </section>

      <section className="panel ops-section" aria-labelledby="task-heading">
        <p className="section-label">VERSIONED TASK / CONFIG</p>
        <h2 id="task-heading">不可变 TaskVersion 清单</h2>
        <p>配置合同固定为 V{runtime.config_schema_version}；任务发布仍使用现有 create/publish 意图命令，Assignment 永远固定原版本。</p>
        <ul className="ops-list">
          {tasks.items.map((task) => (
            <li key={task.id}>
              <div><strong>{task.stable_key}</strong><span>{task.status} · definition revision {task.revision}</span></div>
              <span>{task.versions.map((version) => `V${version.version} ${version.title}`).join(" · ") || "尚未发布"}</span>
            </li>
          ))}
        </ul>
      </section>

      <section className="panel ops-section" aria-labelledby="enrollment-heading">
        <p className="section-label">ENROLLMENT COMMANDS</p>
        <h2 id="enrollment-heading">Enrollment 受控处置</h2>
        <ul className="ops-list">
          {enrollments.items.map((enrollment) => (
            <li key={enrollment.id} className="ops-enrollment">
              <div className="ops-enrollment-heading">
                <div>
                  <strong>{enrollment.learner_display_name}</strong>
                  <span>{enrollment.status} · revision {enrollment.revision} · {enrollment.assignment_statuses.join(" / ") || "无任务"}</span>
                </div>
                <span className="badge">主管：{enrollment.reviewer_display_name}</span>
              </div>
              {enrollment.open_review_status ? (
                <p className="inline-error">已有 {enrollment.open_review_status} Review；Reviewer 重分配与 Enrollment 取消均被状态机阻断。</p>
              ) : null}
              {enrollment.allowed_commands.includes("assign_reviewer") ? (
                <form action={assignEnrollmentReviewer} className="ops-command-form">
                  <input type="hidden" name="enrollment_id" value={enrollment.id} />
                  <input type="hidden" name="revision" value={enrollment.revision} />
                  <label>
                    新 Reviewer UUID
                    <input name="reviewer_id" required pattern="[0-9a-fA-F-]{36}" autoComplete="off" />
                  </label>
                  <label>
                    分配理由
                    <input name="reason" required minLength={10} maxLength={500} autoComplete="off" />
                  </label>
                  <button className="button secondary compact" type="submit">受控分配 Reviewer</button>
                </form>
              ) : null}
              {enrollment.allowed_commands.includes("cancel_enrollment") ? (
                <form action={cancelEnrollment} className="ops-command-form">
                  <input type="hidden" name="enrollment_id" value={enrollment.id} />
                  <input type="hidden" name="revision" value={enrollment.revision} />
                  <label>
                    取消理由
                    <input name="reason" required minLength={10} maxLength={500} autoComplete="off" />
                  </label>
                  <button className="button secondary compact" type="submit">受控取消 Enrollment</button>
                </form>
              ) : null}
            </li>
          ))}
        </ul>
      </section>

      <section className="panel ops-section" aria-labelledby="audit-heading">
        <p className="section-label">SAFE AUDIT VIEW</p>
        <h2 id="audit-heading">最近审计元数据</h2>
        <p>API 最多查询 31 天/100 行；仅安全 allowlist 字段出现在这里，其余字段只显示已裁剪键名。</p>
        <div className="audit-table-wrap">
          <table>
            <thead><tr><th>时间</th><th>动作</th><th>对象</th><th>结果</th><th>安全字段 / 裁剪</th></tr></thead>
            <tbody>
              {audit.items.map((entry) => (
                <tr key={entry.id}>
                  <td>{formatTime(entry.occurred_at)}</td>
                  <td>{entry.action}</td>
                  <td>{entry.resource_type}</td>
                  <td>{entry.result}</td>
                  <td><code>{JSON.stringify(entry.safe_details)}</code><small>裁剪：{entry.redacted_fields.join(", ") || "无"}</small></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </section>
  );
}
