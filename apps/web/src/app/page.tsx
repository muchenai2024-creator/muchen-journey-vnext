import Link from "next/link";

export default function Home() {
  return (
    <section className="hero">
      <p className="eyebrow">探索营 · P0</p>
      <h1>只看一个当前行动，完成一次真实闭环。</h1>
      <p className="lede">
        新人提交真实成果，主管评审固定版本，系统保留事实并给出唯一下一步。
      </p>
      <div className="action-row">
        <Link className="button primary" href="/join">
          使用邀请加入
        </Link>
        <Link className="button secondary" href="/app">
          已加入，进入当前行动
        </Link>
        <Link className="button secondary" href="/review">
          进入主管评审
        </Link>
        <Link className="button secondary" href="/ops">
          查看本地运营状态
        </Link>
      </div>
      <aside className="notice" aria-label="环境说明">
        已启用 vNext 邀请与独立会话；local/test 仍保留显式 fixture 供 walking skeleton 验证。
        真人 UAT、真实外部通知与物理发布证据尚未运行；发布门禁保持 NO_GO。
      </aside>
    </section>
  );
}
