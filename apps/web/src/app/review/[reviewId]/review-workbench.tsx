"use client";

import { useActionState } from "react";

import {
  finalizeReview,
  ReviewActionState,
  startReview,
} from "@/app/actions";

const INITIAL_STATE: ReviewActionState = {};

type RubricDimension = {
  dimension_key: string;
  title: string;
  evidence_expected: string;
  required: boolean;
};

function ActionError({ state }: { state: ReviewActionState }) {
  if (!state.error) return null;
  return (
    <div className="inline-error" role="alert">
      <strong>操作没有完成</strong>
      <span>{state.error}</span>
      {state.requestId ? <code>request ID: {state.requestId}</code> : null}
    </div>
  );
}

export function ReviewWorkbench({
  reviewId,
  revision,
  allowedCommands,
  materialStatus,
  dimensions,
  startIdempotencyKey,
  finalizeIdempotencyKey,
}: {
  reviewId: string;
  revision: number;
  allowedCommands: string[];
  materialStatus: "COMPLETE" | "INCOMPLETE";
  dimensions: RubricDimension[];
  startIdempotencyKey: string;
  finalizeIdempotencyKey: string;
}) {
  const [startState, startAction, startPending] = useActionState(
    startReview,
    INITIAL_STATE,
  );
  const [finalState, finalAction, finalPending] = useActionState(
    finalizeReview,
    INITIAL_STATE,
  );
  const canStart = allowedCommands.includes("start");
  const canFinalize = allowedCommands.includes("approve")
    && allowedCommands.includes("request_revision");

  if (canStart) {
    return (
      <section className="review-actions" aria-labelledby="review-action-title">
        <h2 id="review-action-title">开始评审</h2>
        <p>开始后任务进入“评审中”；当前固定提交版本不会改变。</p>
        <ActionError state={startState} />
        <form action={startAction}>
          <input type="hidden" name="review_id" value={reviewId} />
          <input type="hidden" name="revision" value={revision} />
          <input
            type="hidden"
            name="review_idempotency_key"
            value={startIdempotencyKey}
          />
          <button className="button primary" type="submit" disabled={startPending}>
            {startPending ? "正在开始…" : "开始评审"}
          </button>
        </form>
      </section>
    );
  }

  if (!canFinalize) return null;

  return (
    <section className="review-actions" aria-labelledby="review-action-title">
      <h2 id="review-action-title">Rubric 与最终结论</h2>
      {materialStatus === "INCOMPLETE" ? (
        <p className="inline-error" role="alert">
          材料不完整，服务端不会接受最终结论。请先核对上方缺失项。
        </p>
      ) : (
        <p className="status-meta">
          四个维度都必须评分并写具体反馈；全部达标才能通过，要求修订时至少一项需标为待改进。
        </p>
      )}
      <ActionError state={finalState} />
      <form action={finalAction}>
        <input type="hidden" name="review_id" value={reviewId} />
        <input type="hidden" name="revision" value={revision} />
        <input
          type="hidden"
          name="review_idempotency_key"
          value={finalizeIdempotencyKey}
        />
        {dimensions.map((dimension, index) => (
          <fieldset className="rubric-dimension" key={dimension.dimension_key}>
            <legend>
              {index + 1}. {dimension.title}
            </legend>
            <p>{dimension.evidence_expected}</p>
            <div className="radio-row">
              <label>
                <input
                  type="radio"
                  name={`${dimension.dimension_key}_rating`}
                  value="MEETS"
                  required
                />{" "}
                达标
              </label>
              <label>
                <input
                  type="radio"
                  name={`${dimension.dimension_key}_rating`}
                  value="NEEDS_WORK"
                  required
                />{" "}
                待改进
              </label>
            </div>
            <label htmlFor={`${dimension.dimension_key}-feedback`}>这一维度的具体反馈</label>
            <textarea
              className="rubric-feedback"
              id={`${dimension.dimension_key}-feedback`}
              name={`${dimension.dimension_key}_feedback`}
              minLength={5}
              maxLength={500}
              required
            />
          </fieldset>
        ))}

        <label htmlFor="overall-feedback">总体反馈与下一步建议</label>
        <textarea
          id="overall-feedback"
          name="overall_feedback"
          minLength={10}
          maxLength={2000}
          required
        />
        <fieldset>
          <legend>最终结论</legend>
          <div className="decision-grid">
            <label className="decision-choice">
              <input type="radio" name="overall_decision" value="APPROVE" required />
              <span><strong>通过</strong>四个维度全部达标，任务完成。</span>
            </label>
            <label className="decision-choice">
              <input
                type="radio"
                name="overall_decision"
                value="REQUEST_REVISION"
                required
              />
              <span><strong>要求修订</strong>新人会看到总体反馈并追加新提交版本。</span>
            </label>
          </div>
        </fieldset>
        <button
          className="button primary"
          type="submit"
          disabled={finalPending || materialStatus === "INCOMPLETE"}
        >
          {finalPending ? "正在提交结论…" : "提交不可变最终结论"}
        </button>
      </form>
    </section>
  );
}
