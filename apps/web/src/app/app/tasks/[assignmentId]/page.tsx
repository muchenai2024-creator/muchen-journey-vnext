import { randomUUID } from "node:crypto";

import {
  deleteSubmissionAttachment,
  startAssignment,
} from "@/app/actions";
import { apiRequest, Assignment } from "@/lib/server/api";
import { AttachmentUploader } from "./attachment-uploader";
import { SubmissionComposer } from "./submission-composer";

export const dynamic = "force-dynamic";

export default async function TaskPage({
  params,
  searchParams,
}: {
  params: Promise<{ assignmentId: string }>;
  searchParams: Promise<{ draft?: string; attachment?: string }>;
}) {
  const { assignmentId } = await params;
  const query = await searchParams;
  const assignment = await apiRequest<Assignment>(
    `/api/v1/me/assignments/${encodeURIComponent(assignmentId)}`,
    "LEARNER",
  );
  const canStart = assignment.allowed_commands.includes("start");
  const submitCommand = assignment.allowed_commands.find((command) =>
    ["submit", "submit_revision"].includes(command),
  );
  const latestVersion = assignment.submission?.versions.at(-1);
  const initialBody = assignment.draft?.body
    ?? (submitCommand === "submit_revision" ? latestVersion?.body ?? "" : "");
  const initialAttachmentIds = assignment.draft?.attachment_ids ?? [];

  return (
    <article className="panel content-narrow">
      <p className="eyebrow">
        {assignment.stable_task_key} · Version {assignment.task_version}
      </p>
      <h1>{assignment.task_title}</h1>
      <p className="lede">{assignment.task_purpose}</p>
      <p className="status-meta">
        预计 {assignment.estimated_duration_minutes} 分钟 · 反馈目标 {assignment.feedback_sla_business_days} 个工作日
      </p>
      <h2>完成后你将能够</h2>
      <p>{assignment.learner_outcome}</p>
      <h2>任务步骤</h2>
      <ol className="checklist">
        {assignment.instructions.map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ol>
      <h2>完成标准</h2>
      <ul className="checklist">
        {assignment.completion_criteria.map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ul>

      <h2>需要交付</h2>
      <ul className="checklist">
        {assignment.required_deliverables.map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ul>

      {assignment.reference_materials.length > 0 ? (
        <>
          <h2>参考材料</h2>
          <ul className="checklist">
            {assignment.reference_materials.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </>
      ) : null}

      <h2>工作区</h2>

      {query.draft === "saved" ? (
        <p className="success-text" role="status">草稿已保存，刷新后仍可恢复。</p>
      ) : null}
      {query.attachment === "ready" ? (
        <p className="success-text" role="status">附件已校验并通过本地隔离扫描，可加入提交。</p>
      ) : null}
      {query.attachment === "deleted" ? (
        <p className="success-text" role="status">未绑定附件已删除。</p>
      ) : null}

      {assignment.latest_revision_feedback ? (
        <section className="feedback-callout" aria-labelledby="revision-feedback-title">
          <h3 id="revision-feedback-title">主管要求修订</h3>
          <p>{assignment.latest_revision_feedback}</p>
          <p className="status-meta">旧版本和旧评审保持只读，本次提交会追加新版本。</p>
        </section>
      ) : null}

      {canStart ? (
        <form action={startAssignment}>
          <input type="hidden" name="assignment_id" value={assignment.id} />
          <input type="hidden" name="revision" value={assignment.revision} />
          <button className="button primary" type="submit">开始任务</button>
        </form>
      ) : null}

      {submitCommand ? (
        <>
          {assignment.allowed_attachment_types.length > 0 ? (
            <section className="attachment-workspace" aria-labelledby="attachment-title">
              <h3 id="attachment-title">附件（可选）</h3>
              <p className="status-meta">
                支持 TXT、PDF、PNG、JPEG；单个不超过 {Math.floor(assignment.max_attachment_size_bytes / 1024 / 1024)} MiB。
                文件只在通过 hash、内容类型与本地隔离扫描后可提交。
              </p>
              <AttachmentUploader assignmentId={assignment.id} />
              {assignment.available_attachments.length > 0 ? (
                <ul className="attachment-list">
                  {assignment.available_attachments.map((attachment) => (
                    <li key={attachment.id}>
                      <span>
                        <strong>{attachment.original_filename}</strong>
                        <small>READY · {Math.ceil(attachment.size_bytes / 1024)} KiB</small>
                      </span>
                      <form action={deleteSubmissionAttachment}>
                        <input type="hidden" name="assignment_id" value={assignment.id} />
                        <input type="hidden" name="attachment_id" value={attachment.id} />
                        <button className="button secondary compact" type="submit">删除未绑定附件</button>
                      </form>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="status-meta">暂无 READY 附件；纯文本提交仍可继续。</p>
              )}
            </section>
          ) : (
            <p className="status-meta">当前固定任务版本不接收附件，可直接提交结构化文本。</p>
          )}
          <SubmissionComposer
            assignmentId={assignment.id}
            assignmentRevision={assignment.revision}
            command={submitCommand}
            initialBody={initialBody}
            initialAttachmentIds={initialAttachmentIds}
            attachments={assignment.available_attachments}
            submissionIdempotencyKey={randomUUID()}
            draftIdempotencyKey={randomUUID()}
          />
        </>
      ) : null}

      {assignment.allowed_commands.length === 0 ? (
        <p className="notice">当前版本已锁定，不再提供写入动作。请返回当前行动查看最新状态。</p>
      ) : null}

      {assignment.submission ? (
        <section className="submission-history" aria-labelledby="submission-history-title">
          <h2 id="submission-history-title">提交历史</h2>
          <p className="status-meta">
            当前为 Version {assignment.submission.current_version_no}；历史版本和评审引用永久只读。
          </p>
          {assignment.submission.versions.map((version) => (
            <article className="history-version" key={version.id}>
              <h3>Version {version.version_no}</h3>
              <p className="status-meta">
                {new Intl.DateTimeFormat("zh-CN", { dateStyle: "medium", timeStyle: "short" }).format(new Date(version.created_at))}
                {version.review_status ? ` · 评审 ${version.review_status}` : ""}
              </p>
              <div className="submission">{version.body}</div>
              {version.attachments.length > 0 ? (
                <ul className="checklist">
                  {version.attachments.map((attachment) => (
                    <li key={attachment.id}>{attachment.original_filename}（只读附件）</li>
                  ))}
                </ul>
              ) : null}
              {version.feedback ? (
                <p><strong>该版本反馈：</strong>{version.feedback}</p>
              ) : null}
            </article>
          ))}
        </section>
      ) : null}

      <details>
        <summary>评审会看什么</summary>
        <ul className="checklist">
          {assignment.rubric.dimensions.map((dimension) => (
            <li key={dimension.dimension_key}>
              <strong>{dimension.title}</strong>：{dimension.evidence_expected}
            </li>
          ))}
        </ul>
      </details>
    </article>
  );
}
