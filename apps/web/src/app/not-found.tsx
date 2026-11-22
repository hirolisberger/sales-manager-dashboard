import Link from "next/link";
export default function NotFound() {
  return (
    <div className="panel unexpected-error">
      <p className="eyebrow">404</p>
      <h1>ページが見つかりません</h1>
      <p>URLを確認するか、ホームへお戻りください。</p>
      <Link className="button" href="/">
        ホームへ戻る
      </Link>
    </div>
  );
}
