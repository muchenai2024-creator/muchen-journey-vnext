"use client";

import { useActionState, useState } from "react";

import {
  saveSubmissionDraft,
  submitAssignment,
  SubmissionActionState,
} from "@/app/actions";
import { Attachment } from "@/lib/server/api";

const INITIAL_STATE: SubmissionActionState = {};

export function SubmissionComposer({
  assignmentId,
  assignmentRevision,
  command,
  initialBody,
  initialAttachmentIds,
  attachments,
  submissionIdempotencyKey,
  draftIdempotencyKey,
}: {
  assignmentId: string;
  assignmentRevision: number;
  command: string;
  initialBody: string;
  initialAttachmentIds: string[];
  attachments: Attachment[];
  submissionIdempotencyKey: string;
  draftIdempotencyKey: string;
}) {
  const [body, setBody] = useState(initialBody);
  const [submitState, submitAction, submitPending] = useActionState(
    submitAssignment,
    INITIAL_STATE,
  );
  const [draftState, draftAction, draftPending] = useActionState(
    saveSubmissionDraft,
    INITIAL_STATE,
  );
  const errorState = submitState.error ? submitState : draftState;

  return (
    <form action={submitAction}>
      <input type="hidden" name="assignment_id" value={assignmentId} />
      <input type="hidden" name="revision" value={assignmentRevision} />
      <input
        type="hidden"
        name="submission_idempotency_key"
        value={submissionIdempotencyKey}
      />
      <input type="hidden" name="draft_idempotency_key" value={draftIdempotencyKey} />
      <label htmlFor="submission-body">你的交付内容</label>
      <textarea
        id="submission-body"
        name="body"
        minLength={40}
        maxLength={8000}
        required
        value={body}
        onChange={(event) => setBody(event.target.value)}
      />
      <p className="status-meta">正文会随“保存草稿”写入服务端；提交冲突不会清空当前输入。</p>

      {attachments.length > 0 ? (
        <fieldset>
          <legend>本次使用的 READY 附件</legend>
          {attachments.map((attachment) => (
            <label className="attachment-choice" key={attachment.id}>
              <input
                type="checkbox"
                name="attachment_ids"
                value={attachment.id}
                defaultChecked={initialAttachmentIds.includes(attachment.id)}
              />
              <span>
                {attachment.original_filename} · {Math.ceil(attachment.size_bytes / 1024)} KiB
              </span>
            </label>
          ))}
        </fieldset>
      ) : null}

      {errorState.error ? (
        <div className="inline-error" role="alert">
          <strong>操作没有完成</strong>
          <span>{errorState.error}</span>
          {errorState.requestId ? <code>request ID: {errorState.requestId}</code> : null}
        </div>
      ) : null}

      <div className="action-row">
        <button className="button primary" type="submit" disabled={submitPending || draftPending}>
          {submitPending
            ? "正在提交…"
            : command === "submit_revision"
              ? "提交修订版本"
              : "提交给主管"}
        </button>
        <button
          className="button secondary"
          type="submit"
          formAction={draftAction}
          formNoValidate
          disabled={submitPending || draftPending}
        >
          {draftPending ? "正在保存…" : "保存草稿"}
        </button>
      </div>
    </form>
  );
}
