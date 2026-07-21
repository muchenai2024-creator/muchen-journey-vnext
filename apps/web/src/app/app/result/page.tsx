import { apiRequest, Result, Timeline } from "@/lib/server/api";

export const dynamic = "force-dynamic";

const formatDate = new Intl.DateTimeFormat("zh-CN", {
  dateStyle: "medium",
  timeStyle: "short",
  timeZone: "Asia/Shanghai",
});

const ratingLabels: Record<string, string> = {
  MEETS: "达到要求",
  NEEDS_WORK: "需要改进",
};

function timelineDetail(eventType: string, details: Timeline["items"][number]["details"]) {
  if (eventType === "SUBMISSION_VERSION_CREATED") {
    return `提交版本 ${details.version_no ?? "—"}`;
  }
  if (eventType === "EVALUATION_FINALIZED") {
    return details.decision === "PASS" ? "结论：通过" : "评价已定稿";
  }
  if (eventType.startsWith("NOTIFICATION_")) {
    return "通知记录仅来自本地测试适配器，不代表外部送达";
  }
  return null;
}

export default async function ResultPage() {
  const [result, timeline] = await Promise.all([
    apiRequest<Result>("/api/v1/me/result", "LEARNER"),
    apiRequest<Timeline>("/api/v1/me/timeline?limit=100", "LEARNER"),
  ]);
  return (
    <article className="result-page">
      <header className="panel result-hero">
        <p className="eyebrow">探索营最终结果</p>
        <p className="result-kicker"><span aria-hidden="true">✓</span> 最终人工评价：通过</p>
        <h1>已通过，交接已准备</h1>
        <p className="lede">{result.summary}</p>
        <p className="status-meta">
          结果生成于 <time dateTime={result.created_at}>{formatDate.format(new Date(result.created_at))}</time>
        </p>
      </header>

      <section className="panel result-section" aria-labelledby="feedback-title">
        <p className="section-label">01 · 最终评价</p>
        <h2 id="feedback-title">主管反馈</h2>
        <p className="feedback-summary">{result.evaluation.overall_feedback}</p>
        <ul className="result-rubric">
          {result.evaluation.rubric_feedback.map((item) => (
            <li key={item.dimension_key}>
              <div className="result-rubric-heading">
                <h3>{item.title}</h3>
                <span className="material-status complete">
                  {ratingLabels[item.rating] ?? item.rating}
                </span>
              </div>
              <p>{item.feedback ?? "该历史评价未记录维度级反馈；页面不会补写旧事实。"}</p>
            </li>
          ))}
        </ul>
        <aside className="ai-note" aria-label="AI 摘要状态">
          <strong>AI 摘要未启用</strong>
          <span>{result.ai_summary.message}</span>
        </aside>
      </section>

      <section className="panel result-section" aria-labelledby="handoff-title">
        <p className="section-label">02 · 唯一下一步</p>
        <h2 id="handoff-title">{result.handoff.next_step_title}</h2>
        <div className="handoff-card">
          <div>
            <span className="handoff-owner-label">交接责任人</span>
            <strong>{result.handoff.owner_display_name}</strong>
          </div>
          <p>{result.handoff.instructions}</p>
        </div>
        <p className="status-meta">
          交接事实生成于 <time dateTime={result.handoff.created_at}>{formatDate.format(new Date(result.handoff.created_at))}</time>；刷新或重放不会新建下一步。
        </p>
      </section>

      <section className="panel result-section" aria-labelledby="notification-title">
        <p className="section-label">03 · 通知状态</p>
        <h2 id="notification-title">核心结果不依赖通知</h2>
        <div className={`notification-state notification-${result.notification.status.toLowerCase()}`}>
          <strong>{result.notification.status}</strong>
          <p>{result.notification.display_status}</p>
        </div>
        <p className="notification-disclaimer">
          本地验证范围：{result.notification.delivery_scope}。外部飞书或邮件送达：<strong>未确认</strong>。
          {result.notification.attempt_count > 0 ? ` 已执行 ${result.notification.attempt_count} 次本地尝试。` : ""}
        </p>
      </section>

      <section className="panel result-section" aria-labelledby="timeline-title">
        <p className="section-label">04 · 不可变时间线</p>
        <h2 id="timeline-title">从提交到交接</h2>
        <ol className="result-timeline">
          {timeline.items.map((item) => {
            const detail = timelineDetail(item.event_type, item.details);
            return (
              <li key={item.item_id}>
                <span className="timeline-dot" aria-hidden="true" />
                <div>
                  <time dateTime={item.occurred_at}>{formatDate.format(new Date(item.occurred_at))}</time>
                  <h3>{item.title}</h3>
                  {detail ? <p>{detail}</p> : null}
                </div>
              </li>
            );
          })}
        </ol>
      </section>
    </article>
  );
}
