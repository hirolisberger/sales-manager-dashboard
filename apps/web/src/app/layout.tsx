import type { Metadata } from "next";
import type { ReactNode } from "react";
import { Navigation } from "@/components/navigation";
import "./globals.css";

export const metadata: Metadata = {
  title: { default: "ホーム | 売上管理", template: "%s | 売上管理" },
  description: "小規模店舗の商品と売上を管理するワークスペース。",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="ja">
      <body>
        <a className="skip-link" href="#main-content">
          本文へ移動
        </a>
        <div className="app-shell">
          <aside className="sidebar">
            <div className="brand">
              <span className="brand-icon" aria-hidden="true">
                S
              </span>
              <div>
                <strong>売上管理</strong>
                <span>Sales Manager</span>
              </div>
            </div>
            <Navigation />
            <div className="sidebar-note">
              <span className="local-dot" aria-hidden="true" />
              ローカル確認用
            </div>
          </aside>
          <div className="workspace">
            <header className="topbar">
              <span>店舗ワークスペース</span>
              <span className="environment-badge">ローカル開発</span>
            </header>
            <main id="main-content" tabIndex={-1}>
              {children}
            </main>
            <footer>
              Sales Manager Dashboard<span>商品と売上を、ひとつの場所に。</span>
            </footer>
          </div>
        </div>
      </body>
    </html>
  );
}
