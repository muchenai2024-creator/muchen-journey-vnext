"use client";

import { useActionState } from "react";

import {
  SubmissionActionState,
  uploadSubmissionAttachment,
} from "@/app/actions";

const INITIAL_STATE: SubmissionActionState = {};

export function AttachmentUploader({ assignmentId }: { assignmentId: string }) {
  const [state, action, pending] = useActionState(
    uploadSubmissionAttachment,
    INITIAL_STATE,
  );

  return (
    <form action={action}>
      <input type="hidden" name="assignment_id" value={assignmentId} />
      <label htmlFor="submission-attachment">选择附件</label>
      <input
        id="submission-attachment"
        name="attachment"
        type="file"
        accept="text/plain,application/pdf,image/png,image/jpeg"
        required
      />
      <button className="button secondary" type="submit" disabled={pending}>
        {pending ? "正在上传与校验…" : "上传并校验附件"}
      </button>
      {state.error ? (
        <div className="inline-error" role="alert">
          <strong>附件没有上传</strong>
          <span>{state.error}</span>
          <span>正文与服务端草稿不受影响；可重新选择文件后重试。</span>
          {state.requestId ? <code>request ID: {state.requestId}</code> : null}
        </div>
      ) : null}
    </form>
  );
}
