import "server-only";

import { cookies } from "next/headers";

export type Role = "LEARNER" | "REVIEWER" | "OPERATOR";

export const SESSION_COOKIE = "journey_next_session";
export const JOIN_COOKIE = "journey_next_join";
export const CSRF_COOKIE = "journey_next_csrf";

export type CurrentAction = {
  action_type: string;
  stage: string;
  resource_id: string;
  title: string;
  reason: string;
  allowed_commands: string[];
  revision: number;
  responsible_party: string;
  feedback_expectation: string;
};

export type Assignment = {
  id: string;
  status: string;
  revision: number;
  allowed_commands: string[];
  stable_task_key: string;
  task_version: number;
  task_title: string;
  task_purpose: string;
  learner_outcome: string;
  instructions: string[];
  completion_criteria: string[];
  required_deliverables: string[];
  allowed_attachment_types: string[];
  max_attachment_size_bytes: number;
  reference_materials: string[];
  estimated_duration_minutes: number;
  feedback_sla_business_days: number;
  rubric: {
    version: number;
    dimensions: Array<{
      dimension_key: string;
      title: string;
      evidence_expected: string;
    }>;
  };
  submission: Submission | null;
  draft: SubmissionDraft | null;
  available_attachments: Attachment[];
  latest_revision_feedback: string | null;
};

export type Attachment = {
  id: string;
  assignment_id: string;
  purpose: "SUBMISSION_EVIDENCE";
  original_filename: string;
  content_type: string;
  size_bytes: number;
  sha256: string;
  status: string;
  scan_status: string;
};

export type SubmissionVersion = {
  id: string;
  version_no: number;
  body: string;
  created_at: string;
  attachments: Attachment[];
  review_id: string | null;
  review_status: string | null;
  decision: string | null;
  feedback: string | null;
};

export type Submission = {
  id: string;
  assignment_id: string;
  current_version_no: number;
  versions: SubmissionVersion[];
};

export type SubmissionDraft = {
  body: string;
  attachment_ids: string[];
  revision: number;
  updated_at: string;
  idempotency_replay: boolean;
};

export type ReviewItem = {
  id: string;
  assignment_id: string;
  submission_id: string;
  submission_version_id: string;
  status: string;
  revision: number;
  allowed_commands: string[];
  learner_name: string;
  task_title: string;
  task_version: number;
  submission_version_no: number;
  assigned_at: string;
  started_at: string | null;
  priority_reason: string;
  material_status: "COMPLETE" | "INCOMPLETE";
};

export type ReviewDetail = ReviewItem & {
  submission_body: string;
  task_purpose: string;
  completion_criteria: string[];
  required_deliverables: string[];
  rubric: {
    version: number;
    dimensions: Array<{
      dimension_key: string;
      title: string;
      evidence_expected: string;
      required: boolean;
    }>;
  };
  materials: {
    status: "COMPLETE" | "INCOMPLETE";
    missing_items: string[];
    required_deliverables: string[];
    attachments: Array<{
      id: string;
      original_filename: string;
      content_type: string;
      size_bytes: number;
      status: string;
      scan_status: string;
      download_path: string;
    }>;
  };
  finalized_at: string | null;
  evaluation: {
    id: string;
    decision: "PASS" | "REVISION_REQUIRED";
    overall_decision: "APPROVE" | "REQUEST_REVISION";
    overall_feedback: string;
    rubric_evaluations: Array<{
      dimension_key: string;
      rating: "MEETS" | "NEEDS_WORK";
      feedback: string | null;
    }>;
    feedback_structure_version: number;
    reviewer_id: string;
    review_revision: number;
    created_at: string;
  } | null;
};

export type Result = {
  outcome_id: string;
  status: string;
  decision: "PASS";
  summary: string;
  evaluation: {
    id: string;
    reviewer_id: string;
    decision: "PASS";
    overall_feedback: string;
    rubric_feedback: Array<{
      dimension_key: string;
      title: string;
      rating: string;
      feedback: string | null;
    }>;
    created_at: string;
  };
  handoff: {
    id: string;
    status: "READY";
    owner_user_id: string;
    owner_display_name: string;
    title: string;
    next_step_code: "CONFIRM_HANDOFF";
    next_step_title: string;
    instructions: string;
    created_at: string;
  };
  notification: {
    status: string;
    channel: string | null;
    display_status: string;
    attempt_count: number;
    next_attempt_at: string | null;
    last_error_code: string | null;
    delivered_at: string | null;
    delivery_scope: "LOCAL_TEST_ONLY";
    external_delivery_confirmed: false;
  };
  ai_summary: {
    status: "NOT_ENABLED";
    message: string;
  };
  created_at: string;
};

export type TimelineItem = {
  item_id: string;
  event_type: string;
  title: string;
  occurred_at: string;
  object_type: string;
  object_id: string;
  details: Record<string, string | number | boolean | null>;
};

export type Timeline = {
  items: TimelineItem[];
  next_cursor: string | null;
};

export type OpsTaskDefinition = {
  id: string;
  stable_key: string;
  status: string;
  revision: number;
  content_owner_id: string;
  versions: Array<{ id: string; version: number; title: string; published_at: string }>;
};

export type OpsEnrollment = {
  id: string;
  learner_id: string;
  learner_display_name: string;
  reviewer_id: string;
  reviewer_display_name: string;
  status: string;
  revision: number;
  assignment_statuses: string[];
  open_review_status: string | null;
  allowed_commands: string[];
};

export type OpsAuditEntry = {
  id: string;
  actor_id: string | null;
  action: string;
  resource_type: string;
  resource_id: string | null;
  result: string;
  request_id: string;
  safe_details: Record<string, string | number | boolean>;
  redacted_fields: string[];
  occurred_at: string;
};

export type RuntimeStatus = {
  environment: "local" | "test" | "staging" | "production";
  release: string;
  config_schema_version: 1;
  migration_revision: string;
  api: { status: string; release: string | null };
  database: { status: string };
  worker: {
    status: string;
    release: string | null;
    last_seen_at: string | null;
    stale: boolean | null;
  };
  observability_mode: "LOCAL_STRUCTURED_STDOUT";
  external_observability_confirmed: false;
  metrics: {
    outbox_backlog: number;
    notification_dead: number;
    permission_denials_24h: number;
  };
};

type Envelope<T> = { data: T; request_id: string };
type ErrorEnvelope = {
  error: { code: string; message: string; details?: Record<string, unknown> };
  request_id: string;
};

export class ApiRequestError extends Error {
  constructor(
    readonly code: string,
    message: string,
    readonly requestId: string,
    readonly status: number,
  ) {
    super(message);
    this.name = "ApiRequestError";
  }
}

function assertFixtureBoundary() {
  const allowed = process.env.ALLOW_FIXTURE_IDENTITY === "true";
  const environment = process.env.APP_ENV ?? "local";
  if (!allowed || !["local", "test"].includes(environment)) {
    throw new Error("Fixture identity is disabled outside local/test environments.");
  }
}

export async function apiRequest<T>(
  path: string,
  role: Role,
  init: RequestInit = {},
): Promise<T> {
  const baseUrl = process.env.API_INTERNAL_URL ?? "http://localhost:8000";
  const cookieStore = await cookies();
  const sessionToken = cookieStore.get(SESSION_COOKIE)?.value;
  const csrfToken = cookieStore.get(CSRF_COOKIE)?.value;
  const requestHeaders = new Headers(init.headers);
  requestHeaders.set("Accept", "application/json");
  if (!requestHeaders.has("Content-Type")) {
    requestHeaders.set("Content-Type", "application/json");
  }
  if (sessionToken) {
    const cookieParts = [`${SESSION_COOKIE}=${sessionToken}`];
    if (csrfToken) cookieParts.push(`${CSRF_COOKIE}=${csrfToken}`);
    requestHeaders.set("Cookie", cookieParts.join("; "));
    const method = (init.method ?? "GET").toUpperCase();
    if (!["GET", "HEAD", "OPTIONS"].includes(method) && csrfToken) {
      requestHeaders.set("X-CSRF-Token", csrfToken);
    }
  } else {
    assertFixtureBoundary();
    requestHeaders.set("X-Fixture-Role", role);
  }
  const response = await fetch(new URL(path, baseUrl), {
    ...init,
    cache: "no-store",
    headers: requestHeaders,
  });
  const payload = (await response.json()) as Envelope<T> | ErrorEnvelope;
  if (!response.ok || "error" in payload) {
    const code = "error" in payload ? payload.error.code : "INVALID_RESPONSE";
    const message = "error" in payload ? payload.error.message : "请求失败";
    throw new ApiRequestError(code, message, payload.request_id, response.status);
  }
  return payload.data;
}

export async function anonymousApiRequest<T>(
  path: string,
  init: RequestInit,
): Promise<{ data: T; setCookies: string[] }> {
  const baseUrl = process.env.API_INTERNAL_URL ?? "http://localhost:8000";
  const requestHeaders = new Headers(init.headers);
  requestHeaders.set("Accept", "application/json");
  requestHeaders.set("Content-Type", "application/json");
  const response = await fetch(new URL(path, baseUrl), {
    ...init,
    cache: "no-store",
    headers: requestHeaders,
  });
  const payload = (await response.json()) as Envelope<T> | ErrorEnvelope;
  if (!response.ok || "error" in payload) {
    const code = "error" in payload ? payload.error.code : "INVALID_RESPONSE";
    const message = "error" in payload ? payload.error.message : "请求失败";
    throw new ApiRequestError(code, message, payload.request_id, response.status);
  }
  const responseHeaders = response.headers as Headers & { getSetCookie?: () => string[] };
  const combined = response.headers.get("set-cookie");
  const setCookies = responseHeaders.getSetCookie?.() ?? (combined ? [combined] : []);
  return { data: payload.data, setCookies };
}

export function cookieValue(setCookies: string[], name: string): string | undefined {
  const prefix = `${name}=`;
  for (const header of setCookies) {
    const start = header.indexOf(prefix);
    if (start >= 0) {
      return header.slice(start + prefix.length).split(";", 1)[0];
    }
  }
  return undefined;
}

export async function hasVNextSession(): Promise<boolean> {
  return Boolean((await cookies()).get(SESSION_COOKIE)?.value);
}
