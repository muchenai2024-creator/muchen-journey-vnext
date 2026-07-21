import { randomUUID } from "node:crypto";
import Link from "next/link";

import { apiRequest, ReviewDetail } from "@/lib/server/api";
import { ReviewWorkbench } from "./review-workbench";

export const dynamic = "force-dynamic";

const RATING_LABELS = { MEETS: "达标", NEEDS_WORK: "待改进" } as const;
const DECISION_LABELS = { APPROVE: "通过", REQUEST_REVISION: "要求修订" } as const;

function formatDate(value: string | null): string {
  if (!value) return "—";
  return new Intl.DateTimeFormat("zh-CN", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

export default async function ReviewPage({
  params,
  searchParams,
}: {
  params: Promise<{ reviewId: string }>;
  searchParams: Promise<{ started?: string }>;
}) {
  const { reviewId } = await params;
  const query = await searchParams;
  const review = await apiRequest<ReviewDetail>(
    `/api/v1/reviews/${encodeURIComponent(reviewId)}`,
    "REVIEWER",
  );
  const rubricTitles = new Map(
    review.rubric.dimensions.map((dimension) => [dimension.dimension_key, dimension.title]),
  );

  return (
    <article className="panel review-detail">
      <Link className="back-link" href="/review">← 返回评审队列</Link>
      <p className="eyebrow">
        固定任务 V{review.task_version} · 固定提交 V{review.submission_version_no}
      </p>
      <h1>{review.learner_name} · {review.task_title}</h1>
      <div className="review-status-row">
        <span className="badge">{review.status === "IN_REVIEW" ? "评审中" : review.status === "FINALIZED" ? "已定稿" : "待开始"}</span>
        <span>{review.priority_reason}</span>
        <span>分配于 {formatDate(review.assigned_at)}</span>
      </div>
      {query.started === "yes" ? (
        <p className="success-text" role="status">评审已开始，任务状态已同步为评审中。</p>
      ) : null}

      <section className="review-section" aria-labelledby="task-context-title">
        <h2 id="task-context-title">任务与完成标准</h2>
        <p>{review.task_purpose}</p>
        <ul className="checklist">
          {review.completion_criteria.map((criterion) => <li key={criterion}>{criterion}</li>)}
        </ul>
      </section>

      <section className="review-section" aria-labelledby="materials-title">
        <div className="section-heading-row">
          <h2 id="materials-title">材料完整性</h2>
          <span className={`material-status ${review.materials.status.toLowerCase()}`}>
            {review.materials.status === "COMPLETE" ? "材料完整" : "材料不完整"}
          </span>
        </div>
        <h3>本任务要求的交付</h3>
        <ul className="checklist">
          {review.materials.required_deliverables.map((deliverable) => (
            <li key={deliverable}>{deliverable}</li>
          ))}
        </ul>
        {review.materials.missing_items.length > 0 ? (
          <div className="inline-error" role="alert">
            <strong>缺失或不可用</strong>
            <ul>
              {review.materials.missing_items.map((item) => <li key={item}>{item}</li>)}
            </ul>
          </div>
        ) : null}
        {review.materials.attachments.length > 0 ? (
          <ul className="attachment-list">
            {review.materials.attachments.map((attachment) => (
              <li key={attachment.id}>
                <span>
                  <strong>{attachment.original_filename}</strong>
                  <small>{attachment.content_type} · {Math.ceil(attachment.size_bytes / 1024)} KiB</small>
                </span>
                <span className="badge">{attachment.status} · {attachment.scan_status}</span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="status-meta">此固定版本没有附件；交付内容位于下方正文。</p>
        )}
      </section>

      <section className="review-section" aria-labelledby="submission-title">
        <h2 id="submission-title">固定提交正文</h2>
        <p className="status-meta">该正文属于 SubmissionVersion {review.submission_version_no}，评审不会修改它。</p>
        <div className="submission">{review.submission_body}</div>
      </section>

      <details className="fixed-references">
        <summary>查看固定引用</summary>
        <dl>
          <div><dt>Assignment</dt><dd><code>{review.assignment_id}</code></dd></div>
          <div><dt>Submission</dt><dd><code>{review.submission_id}</code></dd></div>
          <div><dt>SubmissionVersion</dt><dd><code>{review.submission_version_id}</code></dd></div>
        </dl>
      </details>

      {review.evaluation ? (
        <section className="review-section evaluation-history" aria-labelledby="evaluation-title">
          <p className="eyebrow">只读结论历史</p>
          <h2 id="evaluation-title">{DECISION_LABELS[review.evaluation.overall_decision]}</h2>
          <p className="status-meta">
            定稿于 {formatDate(review.evaluation.created_at)} · Review revision {review.evaluation.review_revision}
          </p>
          <div className="feedback-callout">
            <strong>总体反馈</strong>
            <p>{review.evaluation.overall_feedback}</p>
          </div>
          <ol className="evaluation-list">
            {review.evaluation.rubric_evaluations.map((item) => (
              <li key={item.dimension_key}>
                <div className="section-heading-row">
                  <strong>{rubricTitles.get(item.dimension_key) ?? item.dimension_key}</strong>
                  <span className="badge">{RATING_LABELS[item.rating]}</span>
                </div>
                <p>{item.feedback ?? "旧版结论未记录维度级反馈；不补写历史。"}</p>
              </li>
            ))}
          </ol>
        </section>
      ) : (
        <ReviewWorkbench
          reviewId={review.id}
          revision={review.revision}
          allowedCommands={review.allowed_commands}
          materialStatus={review.materials.status}
          dimensions={review.rubric.dimensions}
          startIdempotencyKey={randomUUID()}
          finalizeIdempotencyKey={randomUUID()}
        />
      )}
    </article>
  );
}
