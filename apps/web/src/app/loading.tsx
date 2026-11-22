export default function Loading() {
  return (
    <div className="page-loading" role="status" aria-live="polite">
      <span className="loading-bar" aria-hidden="true" />
      <h1>読み込み中です</h1>
      <p>最新のデータを取得しています。</p>
    </div>
  );
}
