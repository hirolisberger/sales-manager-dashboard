import type { Metadata } from "next";
import { connection } from "next/server";
import { ConnectionError } from "@/components/connection-error";
import { RefreshButton } from "@/components/refresh-button";
import { loadApi } from "@/lib/api";

export const metadata: Metadata = { title: "接続確認" };
export default async function ConnectionPage() {
  await connection();
  const result = await loadApi((api) => api.getHealth());
  return (
    <>
      <div className="page-heading">
        <div>
          <p className="eyebrow">CONNECTION</p>
          <h1>接続確認</h1>
          <p className="page-description">
            画面とAPIが通信できるかを確認します。
          </p>
        </div>
        <RefreshButton />
      </div>
      <section
        className="panel connection-panel"
        aria-labelledby="connection-title"
      >
        <div className="panel-heading">
          <h2 id="connection-title">APIの応答</h2>
        </div>
        {!result.ok ? (
          <ConnectionError requestId={result.requestId} />
        ) : (
          <div className="feedback success-feedback" role="status">
            <span className="feedback-symbol" aria-hidden="true">
              ✓
            </span>
            <div>
              <h2>APIに接続できました</h2>
              <p>Python APIから正常な応答を受け取りました。</p>
            </div>
          </div>
        )}
        <div className="connection-note">
          <h3>確認できること</h3>
          <p>
            APIの応答確認です。データ保存先の状態や、ログイン済みであることを確認する機能ではありません。商品の読み込みはホームで確認できます。
          </p>
        </div>
      </section>
    </>
  );
}
