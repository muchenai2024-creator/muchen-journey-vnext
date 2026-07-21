"use client";

export default function GlobalError({ reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return (
    <section className="content-narrow" role="alert">
      <p className="eyebrow">暂时无法继续</p>
      <h1>操作没有完成</h1>
      <p>已提交的业务事实不会因此回滚。请重试；若仍失败，请联系支持并提供页面上的 request ID。</p>
      <button className="button primary" type="button" onClick={reset}>重试</button>
    </section>
  );
}

