import Link from "next/link";

import { apiRequest, ReviewItem } from "@/lib/server/api";

export const dynamic = "force-dynamic";

function formatWait(value: string): string {
  return new Intl.DateTimeFormat("zh-CN", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

export default async function ReviewQueuePage({
  searchParams,
}: {
  searchParams: Promise<{ finalized?: string }>;
}) {
  const query = await searchParams;
  const queue = await apiRequest<{ items: ReviewItem[] }>("/api/v1/reviews", "REVIEWER");
  return (
    <section className="content-narrow review-queue-page">
      <p className="eyebrow">主管工作台</p>
      <h1>现在先评谁？</h1>
      <p className="lede">只显示明确分配给当前主管、且属于当前组织的待处理评审。</p>
      {query.finalized ? (
        <p className="success-text" role="status">
          {query.finalized === "approved" ? "通过结论已定稿，任务已完成。" : "修订结论已定稿，新人已进入修订状态。"}
        </p>
      ) : null}
      {queue.items.length === 0 ? (
        <p className="notice">当前没有待处理评审。</p>
      ) : (
        <ol className="queue">
          {queue.items.map((item, index) => (
            <li key={item.id}>
              <Link className="queue-item" href={`/review/${item.id}`}>
                <div className="section-heading-row">
                  <span className="badge">优先级 {index + 1} · {item.status === "IN_REVIEW" ? "评审中" : "待开始"}</span>
                  <span className={`material-status ${item.material_status.toLowerCase()}`}>
                    {item.material_status === "COMPLETE" ? "材料完整" : "材料不完整"}
                  </span>
                </div>
                <strong className="queue-title">{item.learner_name} · {item.task_title}</strong>
                <span>{item.priority_reason}</span>
                <span className="queue-meta">
                  任务 V{item.task_version} · 提交 V{item.submission_version_no} · 分配于 {formatWait(item.assigned_at)}
                </span>
              </Link>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}
