"use server";

import { createHash, randomUUID } from "node:crypto";
import { revalidatePath } from "next/cache";
import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import {
  anonymousApiRequest,
  ApiRequestError,
  apiRequest,
  cookieValue,
  CSRF_COOKIE,
  JOIN_COOKIE,
  SESSION_COOKIE,
} from "@/lib/server/api";

const UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

function requiredUuid(data: FormData, key: string): string {
  const value = data.get(key);
  if (typeof value !== "string" || !UUID_PATTERN.test(value)) {
    throw new Error("资源标识无效。请刷新页面后重试。");
  }
  return value;
}

function requiredRevision(data: FormData): number {
  const value = Number(data.get("revision"));
  if (!Number.isSafeInteger(value) || value < 1) {
    throw new Error("版本信息无效。请刷新页面后重试。");
  }
  return value;
}

function commandHeaders(): HeadersInit {
  return { "Idempotency-Key": randomUUID() };
}

function requiredIdempotencyKey(data: FormData, key: string): string {
  const value = data.get(key);
  if (typeof value !== "string" || !UUID_PATTERN.test(value)) {
    throw new Error("重试标识无效。请刷新页面后重试。");
  }
  return value;
}

function attachmentIds(data: FormData): string[] {
  const values = data.getAll("attachment_ids");
  if (values.length > 5 || values.some((value) => typeof value !== "string" || !UUID_PATTERN.test(value))) {
    throw new Error("附件选择无效。请刷新页面后重试。");
  }
  return values as string[];
}

export type SubmissionActionState = {
  error?: string;
  requestId?: string;
};

function submissionError(error: unknown): SubmissionActionState {
  if (error instanceof ApiRequestError) {
    return { error: error.message, requestId: error.requestId };
  }
  return { error: error instanceof Error ? error.message : "操作没有完成，请重试。" };
}

const JOIN_SUMMARY_COOKIE = "journey_next_join_summary";

function cookieSecure(): boolean {
  return ["staging", "production"].includes(process.env.APP_ENV ?? "local");
}

function safeJoinError(error: unknown): never {
  if (error instanceof ApiRequestError) {
    const query = new URLSearchParams({ code: error.code, request_id: error.requestId });
    redirect(`/join?${query.toString()}`);
  }
  throw error;
}

export async function exchangeInvite(data: FormData) {
  const token = data.get("token");
  if (typeof token !== "string" || token.length < 32 || token.length > 256) {
    redirect("/join?code=INVITE_EXPIRED_OR_REVOKED");
  }
  let exchange: {
    data: { purpose: string; expires_at: string; csrf_token: string };
    setCookies: string[];
  };
  try {
    exchange = await anonymousApiRequest("/api/v1/join/exchange", {
      method: "POST",
      body: JSON.stringify({ token, return_to: "/app" }),
    });
  } catch (error) {
    safeJoinError(error);
  }
  const joinToken = cookieValue(exchange.setCookies, JOIN_COOKIE);
  if (!joinToken) throw new Error("API 未返回安全加入上下文。");
  const cookieStore = await cookies();
  const maxAge = Math.max(
    1,
    Math.floor((new Date(exchange.data.expires_at).getTime() - Date.now()) / 1000),
  );
  const options = { path: "/", sameSite: "lax" as const, secure: cookieSecure(), maxAge };
  cookieStore.set(JOIN_COOKIE, joinToken, { ...options, httpOnly: true });
  cookieStore.set(CSRF_COOKIE, exchange.data.csrf_token, { ...options, httpOnly: false });
  cookieStore.set(
    JOIN_SUMMARY_COOKIE,
    Buffer.from(
      JSON.stringify({ purpose: exchange.data.purpose, expires_at: exchange.data.expires_at }),
    ).toString("base64url"),
    { ...options, httpOnly: true },
  );
  redirect("/join");
}

export async function confirmIdentity(data: FormData) {
  const displayName = data.get("display_name");
  const acceptedPurpose = data.get("accepted_purpose") === "yes";
  if (typeof displayName !== "string" || !displayName.trim() || displayName.length > 120) {
    redirect("/join?code=VALIDATION_FAILED");
  }
  if (!acceptedPurpose) redirect("/join?code=PURPOSE_NOT_ACCEPTED");
  const cookieStore = await cookies();
  const joinToken = cookieStore.get(JOIN_COOKIE)?.value;
  const csrfToken = cookieStore.get(CSRF_COOKIE)?.value;
  if (!joinToken || !csrfToken) redirect("/join?code=INVITE_EXPIRED_OR_REVOKED");
  let confirmation: {
    data: { expires_at: string; csrf_token: string };
    setCookies: string[];
  };
  try {
    confirmation = await anonymousApiRequest("/api/v1/identity/confirm", {
      method: "POST",
      headers: {
        Cookie: `${JOIN_COOKIE}=${joinToken}; ${CSRF_COOKIE}=${csrfToken}`,
        "X-CSRF-Token": csrfToken,
      },
      body: JSON.stringify({
        display_name: displayName.trim(),
        accepted_purpose: true,
        return_to: "/app",
      }),
    });
  } catch (error) {
    safeJoinError(error);
  }
  const sessionToken = cookieValue(confirmation.setCookies, SESSION_COOKIE);
  if (!sessionToken) throw new Error("API 未返回安全 vNext 会话。");
  const maxAge = Math.max(
    1,
    Math.floor((new Date(confirmation.data.expires_at).getTime() - Date.now()) / 1000),
  );
  const options = { path: "/", sameSite: "lax" as const, secure: cookieSecure(), maxAge };
  cookieStore.set(SESSION_COOKIE, sessionToken, { ...options, httpOnly: true });
  cookieStore.set(CSRF_COOKIE, confirmation.data.csrf_token, { ...options, httpOnly: false });
  cookieStore.delete(JOIN_COOKIE);
  cookieStore.delete(JOIN_SUMMARY_COOKIE);
  revalidatePath("/app");
  redirect("/app");
}

export async function logoutSession() {
  await apiRequest("/api/v1/session/logout", "LEARNER", { method: "POST" });
  const cookieStore = await cookies();
  cookieStore.delete(SESSION_COOKIE);
  cookieStore.delete(CSRF_COOKIE);
  redirect("/");
}

export async function startAssignment(data: FormData) {
  const assignmentId = requiredUuid(data, "assignment_id");
  const expectedRevision = requiredRevision(data);
  await apiRequest(`/api/v1/me/assignments/${assignmentId}/start`, "LEARNER", {
    method: "POST",
    headers: commandHeaders(),
    body: JSON.stringify({ expected_revision: expectedRevision }),
  });
  revalidatePath("/app");
  redirect(`/app/tasks/${assignmentId}`);
}

export async function submitAssignment(
  _previousState: SubmissionActionState,
  data: FormData,
): Promise<SubmissionActionState> {
  const assignmentId = requiredUuid(data, "assignment_id");
  const expectedRevision = requiredRevision(data);
  const idempotencyKey = requiredIdempotencyKey(data, "submission_idempotency_key");
  const body = data.get("body");
  if (typeof body !== "string" || body.trim().length < 40 || body.length > 8_000) {
    return { error: "提交内容需为 40–8000 个字符。草稿仍保留在当前页面。" };
  }
  try {
    await apiRequest(`/api/v1/me/assignments/${assignmentId}/submissions`, "LEARNER", {
      method: "POST",
      headers: { "Idempotency-Key": idempotencyKey },
      body: JSON.stringify({
        expected_revision: expectedRevision,
        body: body.trim(),
        attachment_ids: attachmentIds(data),
      }),
    });
  } catch (error) {
    return submissionError(error);
  }
  revalidatePath("/app");
  redirect("/app");
}

export async function saveSubmissionDraft(
  _previousState: SubmissionActionState,
  data: FormData,
): Promise<SubmissionActionState> {
  const assignmentId = requiredUuid(data, "assignment_id");
  const expectedRevision = requiredRevision(data);
  const idempotencyKey = requiredIdempotencyKey(data, "draft_idempotency_key");
  const body = data.get("body");
  if (typeof body !== "string" || body.length > 8_000) {
    return { error: "草稿内容不能超过 8000 个字符。" };
  }
  try {
    await apiRequest(`/api/v1/me/assignments/${assignmentId}/draft`, "LEARNER", {
      method: "PUT",
      headers: { "Idempotency-Key": idempotencyKey },
      body: JSON.stringify({
        expected_revision: expectedRevision,
        body,
        attachment_ids: attachmentIds(data),
      }),
    });
  } catch (error) {
    return submissionError(error);
  }
  revalidatePath(`/app/tasks/${assignmentId}`);
  redirect(`/app/tasks/${assignmentId}?draft=saved`);
}

const ALLOWED_ATTACHMENT_TYPES = new Set([
  "text/plain",
  "application/pdf",
  "image/png",
  "image/jpeg",
]);

export async function uploadSubmissionAttachment(
  _previousState: SubmissionActionState,
  data: FormData,
): Promise<SubmissionActionState> {
  let assignmentId: string;
  try {
    assignmentId = requiredUuid(data, "assignment_id");
    const file = data.get("attachment");
    if (!(file instanceof File) || file.size < 1) {
      return { error: "请选择一个非空附件。" };
    }
    if (file.size > 5 * 1024 * 1024) {
      return { error: "附件不能超过 5 MiB。" };
    }
    if (!ALLOWED_ATTACHMENT_TYPES.has(file.type)) {
      return { error: "附件只支持 TXT、PDF、PNG 或 JPEG。" };
    }
    const content = Buffer.from(await file.arrayBuffer());
    const sha256 = createHash("sha256").update(content).digest("hex");
    const presigned = await apiRequest<{ id: string; upload_url: string }>(
      "/api/v1/attachments/presign",
      "LEARNER",
      {
        method: "POST",
        headers: commandHeaders(),
        body: JSON.stringify({
          assignment_id: assignmentId,
          purpose: "SUBMISSION_EVIDENCE",
          original_filename: file.name,
          content_type: file.type,
          size_bytes: file.size,
          sha256,
        }),
      },
    );
    await apiRequest(presigned.upload_url, "LEARNER", {
      method: "PUT",
      headers: { "Content-Type": file.type, "Content-Length": String(file.size) },
      body: content,
    });
    await apiRequest(`/api/v1/attachments/${presigned.id}/complete`, "LEARNER", {
      method: "POST",
      headers: commandHeaders(),
      body: JSON.stringify({ content_type: file.type, size_bytes: file.size, sha256 }),
    });
  } catch (error) {
    return submissionError(error);
  }
  revalidatePath(`/app/tasks/${assignmentId}`);
  redirect(`/app/tasks/${assignmentId}?attachment=ready`);
}

export async function deleteSubmissionAttachment(data: FormData) {
  const assignmentId = requiredUuid(data, "assignment_id");
  const attachmentId = requiredUuid(data, "attachment_id");
  await apiRequest(`/api/v1/attachments/${attachmentId}`, "LEARNER", { method: "DELETE" });
  revalidatePath(`/app/tasks/${assignmentId}`);
  redirect(`/app/tasks/${assignmentId}?attachment=deleted`);
}

export type ReviewActionState = {
  error?: string;
  requestId?: string;
};

function reviewError(error: unknown): ReviewActionState {
  if (error instanceof ApiRequestError) {
    return { error: error.message, requestId: error.requestId };
  }
  return { error: error instanceof Error ? error.message : "操作没有完成，请重试。" };
}

export async function startReview(
  _previousState: ReviewActionState,
  data: FormData,
): Promise<ReviewActionState> {
  let reviewId: string;
  try {
    reviewId = requiredUuid(data, "review_id");
    const expectedRevision = requiredRevision(data);
    const idempotencyKey = requiredIdempotencyKey(data, "review_idempotency_key");
    await apiRequest(`/api/v1/reviews/${reviewId}/start`, "REVIEWER", {
      method: "POST",
      headers: { "Idempotency-Key": idempotencyKey },
      body: JSON.stringify({ expected_revision: expectedRevision }),
    });
  } catch (error) {
    return reviewError(error);
  }
  revalidatePath("/review");
  redirect(`/review/${reviewId}?started=yes`);
}

const REVIEW_RUBRIC_KEYS = [
  "problem_clarity",
  "evidence_quality",
  "action_feasibility",
  "validation_design",
] as const;

export async function finalizeReview(
  _previousState: ReviewActionState,
  data: FormData,
): Promise<ReviewActionState> {
  let reviewId: string;
  let overallDecision: "APPROVE" | "REQUEST_REVISION";
  try {
    reviewId = requiredUuid(data, "review_id");
    const expectedRevision = requiredRevision(data);
    const idempotencyKey = requiredIdempotencyKey(data, "review_idempotency_key");
    const decision = data.get("overall_decision");
    if (decision !== "APPROVE" && decision !== "REQUEST_REVISION") {
      throw new Error("请选择通过或要求修订。");
    }
    overallDecision = decision;
    const overallFeedback = data.get("overall_feedback");
    if (
      typeof overallFeedback !== "string"
      || overallFeedback.trim().length < 10
      || overallFeedback.length > 2_000
    ) {
      throw new Error("总体反馈需为 10–2000 个字符。");
    }
    const rubricEvaluations = REVIEW_RUBRIC_KEYS.map((dimensionKey) => {
      const rating = data.get(`${dimensionKey}_rating`);
      const feedback = data.get(`${dimensionKey}_feedback`);
      if (rating !== "MEETS" && rating !== "NEEDS_WORK") {
        throw new Error("请完成全部 Rubric 评分。");
      }
      if (typeof feedback !== "string" || feedback.trim().length < 5 || feedback.length > 500) {
        throw new Error("每个 Rubric 维度需填写 5–500 个字符的具体反馈。");
      }
      return {
        dimension_key: dimensionKey,
        rating,
        feedback: feedback.trim(),
      };
    });
    await apiRequest(`/api/v1/reviews/${reviewId}/finalize`, "REVIEWER", {
      method: "POST",
      headers: { "Idempotency-Key": idempotencyKey },
      body: JSON.stringify({
        expected_revision: expectedRevision,
        overall_decision: overallDecision,
        overall_feedback: overallFeedback.trim(),
        rubric_evaluations: rubricEvaluations,
      }),
    });
  } catch (error) {
    return reviewError(error);
  }
  revalidatePath("/review");
  redirect(`/review?finalized=${overallDecision === "APPROVE" ? "approved" : "revision"}`);
}

function requiredReason(data: FormData): string {
  const reason = data.get("reason");
  if (typeof reason !== "string" || reason.trim().length < 10 || reason.length > 500) {
    throw new Error("运营理由需为 10–500 个字符。");
  }
  return reason.trim();
}

export async function assignEnrollmentReviewer(data: FormData) {
  const enrollmentId = requiredUuid(data, "enrollment_id");
  const reviewerId = requiredUuid(data, "reviewer_id");
  const expectedRevision = requiredRevision(data);
  await apiRequest(`/api/v1/ops/enrollments/${enrollmentId}/reviewer`, "OPERATOR", {
    method: "PUT",
    headers: commandHeaders(),
    body: JSON.stringify({
      expected_revision: expectedRevision,
      reviewer_id: reviewerId,
      reason: requiredReason(data),
    }),
  });
  revalidatePath("/ops");
  redirect("/ops?updated=reviewer");
}

export async function cancelEnrollment(data: FormData) {
  const enrollmentId = requiredUuid(data, "enrollment_id");
  const expectedRevision = requiredRevision(data);
  await apiRequest(`/api/v1/ops/enrollments/${enrollmentId}/cancel`, "OPERATOR", {
    method: "POST",
    headers: commandHeaders(),
    body: JSON.stringify({
      expected_revision: expectedRevision,
      reason: requiredReason(data),
    }),
  });
  revalidatePath("/ops");
  redirect("/ops?updated=cancelled");
}
