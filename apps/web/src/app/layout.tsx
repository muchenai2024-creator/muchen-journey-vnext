import type { Metadata } from "next";
import Link from "next/link";

import "./globals.css";

export const metadata: Metadata = {
  title: {
    default: "Muchen Journey",
    template: "%s · Muchen Journey",
  },
  description: "一个清晰连接当前任务、主管反馈与下一步的成长闭环。",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="zh-CN">
      <body>
        <a className="skip-link" href="#main-content">
          跳到主要内容
        </a>
        <header className="site-header">
          <Link className="brand" href="/">
            Muchen Journey
          </Link>
          <nav aria-label="主要导航">
            <Link href="/app">新人当前行动</Link>
            <Link href="/review">主管评审</Link>
            <Link href="/ops">本地运营</Link>
          </nav>
        </header>
        <main id="main-content" className="page-shell">
          {children}
        </main>
        <footer className="site-footer">vNext Greenfield · WP-06 本地候选 · 发布 NO_GO</footer>
      </body>
    </html>
  );
}
