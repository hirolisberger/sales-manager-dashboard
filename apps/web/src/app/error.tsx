"use client";
export default function ErrorPage({
  retry,
}: {
  error: unknown;
  retry: () => void;
}) {
  return (
    <div className="panel unexpected-error" role="alert">
      <h1>画面を表示できませんでした</h1>
      <p>時間をおいて、もう一度お試しください。</p>
      <button type="button" className="button" onClick={retry}>
        もう一度試す
      </button>
    </div>
  );
}
