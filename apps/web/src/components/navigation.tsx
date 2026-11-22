"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";

export function Navigation() {
  const pathname = usePathname();
  return (
    <nav aria-label="メインナビゲーション">
      <p className="nav-label">ワークスペース</p>
      <ul className="nav-list">
        {[
          { href: "/", label: "ホーム", mark: "01" },
          { href: "/connection", label: "接続確認", mark: "02" },
        ].map(({ href, label, mark }) => (
          <li key={href}>
            <Link
              href={href}
              prefetch={false}
              aria-current={pathname === href ? "page" : undefined}
            >
              <span className="nav-mark" aria-hidden="true">
                {mark}
              </span>
              {label}
            </Link>
          </li>
        ))}
      </ul>
      <p className="nav-label upcoming-label">これから使える機能</p>
      <ul className="upcoming-list">
        {["商品管理", "売上登録", "売上検索・集計"].map((label) => (
          <li key={label}>
            <span>{label}</span>
            <span className="upcoming-tag">準備中</span>
          </li>
        ))}
      </ul>
    </nav>
  );
}
