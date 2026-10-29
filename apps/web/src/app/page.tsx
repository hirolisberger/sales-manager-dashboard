export default function Home() {
  return (
    <main>
      <section className="setup" aria-labelledby="page-title">
        <p className="eyebrow">SALES MANAGER</p>
        <h1 id="page-title">売上管理システム</h1>
        <p className="description">
          小規模店舗の商品別売上を管理するシステムを開発しています。
        </p>
        <div className="status">
          <span className="status-mark" aria-hidden="true" />
          <p>Next.jsの起動を確認できました。</p>
        </div>
        <p className="note">
          Day 2：開発環境の準備。商品登録や売上登録は、これから実装します。
        </p>
      </section>
    </main>
  );
}
