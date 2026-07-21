import Link from "next/link";

import { logoutSession } from "@/app/actions";
import { apiRequest, CurrentAction, hasVNextSession } from "@/lib/server/api";

export const dynamic = "force-dynamic";

export default async function LearnerHome() {
  const [action, hasSession] = await Promise.all([
    apiRequest<CurrentAction>("/api/v1/me/current-action", "LEARNER"),
    hasVNextSession(),
  ]);
  const opensTask = ["START_OR_CONTINUE_TASK", "REVISE_SUBMISSION"].includes(
    action.action_type,
  );
  const opensResult = action.action_type === "VIEW_RESULT_OR_HANDOFF";

  return (
    <section className="content-narrow">
      <p className="eyebrow">你的当前行动</p>
      <article className="status-card">
        <span className="badge">{action.stage}</span>
        <h1>{action.title}</h1>
        <p>{action.reason}</p>
        <p className="status-meta">
          反馈责任人：{action.responsible_party} · 处理预期：{action.feedback_expectation}
        </p>
        {opensTask || opensResult ? (
          <div className="action-row">
            <Link
              className="button primary"
              href={opensResult ? "/app/result" : `/app/tasks/${action.resource_id}`}
            >
              {opensResult ? "查看结果与交接" : action.title}
            </Link>
          </div>
        ) : null}
      </article>
      {hasSession ? (
        <form action={logoutSession}>
          <button className="button secondary" type="submit">退出 vNext 会话</button>
        </form>
      ) : null}
    </section>
  );
}
