import Link from "next/link";
import { connection } from "next/server";
import { ConnectionError } from "@/components/connection-error";
import { RefreshButton } from "@/components/refresh-button";
import { loadApi } from "@/lib/api";

const yen = new Intl.NumberFormat("ja-JP", {
  style: "currency",
  currency: "JPY",
});

export default async function Home() {
  await connection();
  const result = await loadApi((api) => api.getProductPreview());
  return (
    <>
      <div className="page-heading">
        <div>
          <p className="eyebrow">WORKSPACE</p>
          <h1>ホーム</h1>
          <p className="page-description">
            日々の商品と売上を、ここから管理します。
          </p>
        </div>
        <RefreshButton />
      </div>
      <section className="welcome-panel" aria-labelledby="welcome-title">
        <div>
          <span className="section-kicker">はじめに</span>
          <h2 id="welcome-title">売上管理の準備を整えましょう</h2>
          <p>登録済みの商品を読み込み、データ接続を確認できます。</p>
        </div>
        <Link className="text-link" href="/connection" prefetch={false}>
          接続状態を確認する <span aria-hidden="true">→</span>
        </Link>
      </section>
      <section className="panel" aria-labelledby="products-title">
        <div className="panel-heading">
          <div>
            <h2 id="products-title">登録済みの商品</h2>
            <p>有効な商品の先頭3件を表示します。</p>
          </div>
          <span className="subtle-badge">参照のみ</span>
        </div>
        {!result.ok ? (
          <ConnectionError requestId={result.requestId} />
        ) : result.data.items.length === 0 ? (
          <div className="empty-state">
            <span className="empty-icon" aria-hidden="true">
              ＋
            </span>
            <h3>商品はまだ登録されていません</h3>
            <p>
              データの読み込みは成功しています。商品を登録すると、ここに表示されます。
            </p>
          </div>
        ) : (
          <>
            <div className="table-scroll">
              <table>
                <caption className="sr-only">
                  登録済みの有効商品、最大3件
                </caption>
                <thead>
                  <tr>
                    <th scope="col">商品</th>
                    <th scope="col">商品コード</th>
                    <th scope="col" className="amount">
                      税込標準単価
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {result.data.items.map((item) => (
                    <tr key={item.id}>
                      <th scope="row">{item.name}</th>
                      <td className="product-code">{item.code}</td>
                      <td className="amount">
                        {yen.format(item.default_unit_price_yen)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {result.data.next_cursor && (
              <p className="panel-footnote">
                ほかにも有効な商品が登録されています。
              </p>
            )}
          </>
        )}
      </section>
      <p className="workspace-note">
        商品・売上の入力画面は準備中です。この画面からデータは変更されません。
      </p>
    </>
  );
}
