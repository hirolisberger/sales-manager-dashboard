import { RefreshButton } from "./refresh-button";

export function ConnectionError({ requestId }: { requestId?: string }) {
  return (
    <div className="feedback error-feedback" role="alert">
      <span className="feedback-symbol" aria-hidden="true">
        !
      </span>
      <div>
        <h2>データを取得できませんでした</h2>
        <p>
          接続先とAPI・データ保存先の起動状態を確認し、もう一度お試しください。
        </p>
        {requestId && <p className="request-id">確認用ID：{requestId}</p>}
        <RefreshButton />
      </div>
    </div>
  );
}
