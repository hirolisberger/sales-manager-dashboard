# 【Day 11】Next.jsとPython APIをつなぐ：共通レイアウトと通信処理

シリーズ：**Next.js・Python・AWSで作る売上管理システム**

公開予定：2026年12月11日（日本時間）。開発・レビューとQiitaへの公開は別に管理しています。

## はじめに

[Day 10](https://github.com/hirolisberger/sales-manager-dashboard/blob/day10/qiita/day10-sales-correction-and-cancellation.md)までで、商品と売上のAPIを作りました。今回はNext.jsの起動確認ページから進めて、Python APIのデータを画面に表示します。

いきなり登録フォームを作る前に、共通レイアウト・ナビゲーション・通信処理をそろえます。接続できたときだけでなく、商品が0件のとき、取得に時間がかかるとき、APIが止まったときにも、次の操作が分かる状態を作りました。

## この記事の到達点

- 共通レイアウトの中でホームと接続確認を切り替える
- Python APIから有効商品の先頭3件を読み、税込標準単価を表示する
- 読込中・空結果・通信失敗と、更新による復帰を扱う
- Server ComponentsとClient Componentsの役割を分ける

今回は参照だけです。商品管理画面はDay 12、売上入力はDay 13、売上検索・訂正の画面はDay 14で作ります。集計値やグラフもまだ表示しません。

環境はNode.js 24.22.2 / npm 11.19.1 / Next.js 16.4.6 / React 19.3.1 / TypeScript 6.0.3。Python APIとMiniStackは前回までの実装を使い、新しい依存は追加せず、監査で指摘されたNext.jsを16.4.3から16.4.6へパッチ更新しました。公式資料とインストール済みNext.js内のガイドは2026年11月22日に確認しました。

固定ロックからの再導入でも、その後に公表された問題は監査対象になります。今回はnpmがNext.js 16.4.3に中程度の指摘を報告したため、[公式リリース16.4.6](https://github.com/vercel/next.js/releases/tag/v16.4.6)と[公式アドバイザリー](https://github.com/vercel/next.js/security/advisories/GHSA-vvgp-ww4w-46vf)を確認し、同じ16.4系のパッチへ更新しました。更新後のnpm監査は検出0件です。これは検証日時点の結果で、過去の承認済みタグは変更しません。

リポジトリは[sales-manager-dashboard](https://github.com/hirolisberger/sales-manager-dashboard)です。以下のday11リンクは完成時点のタグを使う予定で、レビュー待ち時点ではタグ未作成です。Qiita公開前に有効性を確認します。

## 1. 画面の共通部分をlayoutへ置く

サイドバー、店舗ワークスペースのヘッダー、本文、フッターをlayout.tsxへまとめました。ホームと接続確認のページは本文だけを担当します。

| ファイル | 役割 |
| --- | --- |
| src/app/layout.tsx | 共通の枠とメタデータ |
| src/app/page.tsx | 商品の参照・空結果・取得失敗 |
| src/app/connection/page.tsx | APIのhealthを表示 |
| src/components/navigation.tsx | 現在のURLに応じた選択表示 |
| src/components/refresh-button.tsx | 表示の再取得と更新中の状態 |

未実装の商品管理・売上入力などは準備中のテキストにしています。存在しない画面へのリンクは作らず、今回使える二つのページだけをナビゲーションに置きました。

デスクトップではサイドバー、狭い画面では横並びのナビゲーションにします。現在位置にはaria-currentを付け、キーボードのフォーカスと本文へのスキップリンクも用意しました。

## 2. Python APIを呼ぶ場所を決める

今回の通信は次の順番です。

```text
ブラウザー → Next.jsサーバー → Python API → MiniStack
```

ページはServer Componentsのまま、サーバー専用のlib/api.tsからAPIクライアントを呼びます。API_BASE_URLはNext.jsの環境変数で、NEXT_PUBLIC_を付けません。lib/api.tsにはserver-onlyをimportし、Client Componentsへ誤って取り込むとビルドで分かる境界にします。[Next.jsのServer / Client資料](https://nextjs.org/docs/app/getting-started/server-and-client-components)

ブラウザーはNext.jsにだけ接続するため、今回はPythonへブラウザー向けCORS設定を追加しません。AWSのSDKや認証情報も画面へ持ち込みません。

Client Componentsにしたのは、usePathnameを使うナビゲーション、router.refreshを呼ぶ更新ボタン、例外用のerror.tsxです。画面全体へuse clientを付ける必要はありません。

## 3. APIクライアントで失敗の扱いをそろえる

lib/api-client.tsでは、healthと商品プレビューの二つのGETを用意しました。商品は既存APIのis_active=true&limit=3で読みます。商品UUID順の先頭3件で、商品全体の総数や売上を表す値ではありません。

通信には次を明示します。

- cache: no-storeでデータを再取得する
- redirect: errorでリダイレクトを追わない
- AbortSignal.timeoutで5秒を上限にする
- JSONのContent-Typeと、表示に必要な値の型・範囲を検証する

TypeScriptで型を書いても、実際に届いたJSONの内容は保証されません。税込標準単価が文字列だったり、itemsが配列でなかったりした場合も、取得失敗として扱います。[Next.jsのデータ取得資料](https://nextjs.org/docs/app/getting-started/fetching-data)

HTTPエラーや通信例外の本文は画面へ渡さず、共通メッセージへ変換します。APIが返したX-Request-IDがUUIDなら、問い合わせやログ照合に使う確認用IDだけを表示します。

Day 11の接続先はloopbackのHTTPだけです。未設定や外部ホストでは接続せず、別URLへ自動で切り替えません。これはローカル開発の境界で、AWSの接続先と認証は配備するDayで設計します。

## 4. ビルドとリクエスト時の取得を分ける

ページではconnection()を待ってからAPIを呼びます。

```tsx
export default async function Home() {
  await connection();
  const result = await loadApi((api) => api.getProductPreview());
  // result.okに応じて商品・空結果・取得失敗を表示する
}
```

このコードは責務を示す抜粋で、実際のページは[page.tsx](https://github.com/hirolisberger/sales-manager-dashboard/blob/day11/apps/web/src/app/page.tsx)です。

APIが止まっていてもビルドを作り、アクセス時にデータを取得する構成です。connection()はリクエスト到着を待つAPIとして、採用版のガイドを確認しました。[Next.jsのconnection資料](https://nextjs.org/docs/app/api-reference/functions/connection)

動的なサーバー処理を使うので、完成した静的ファイルだけをS3へ置く構成では動きません。AWS上のNext.jsの動かし方はDay 22〜23で確認します。

## 5. 0件と失敗を別の表示にする

商品が0件なら、通信は成功しています。「商品はまだ登録されていません」と表示します。API停止や不正な応答なら「データを取得できませんでした」と更新ボタンを表示します。

loading.tsxは「読み込み中です」。APIデータの取得をページ側で行うことで、共通レイアウトを表示したまま結果を待ちます。更新ボタンにはuseTransitionを使い、再取得中は操作を無効化します。

「接続確認」はhealthの応答だけを確認します。保存先が止まったりテーブルが見つからなかったりしても、healthは成功し得ます。ホームの商品取得と同じ成功判定にしません。

想定する接続失敗は結果として表示し、予期しない例外用にerror.tsxも用意しました。採用したNext.js 16.4.6では、再取得を伴うretryプロパティを使います。[Next.jsのエラー処理資料](https://nextjs.org/docs/app/getting-started/error-handling)

## 6. ローカルで画面を開く

作業ディレクトリはsales-manager-dashboard/です。[Day 11の全コマンド解説](https://github.com/hirolisberger/sales-manager-dashboard/blob/day11/docs/DAY11_COMMANDS.md)に従い、固定バージョンのNode.js・uv、MiniStackと確認専用テーブルを準備します。

ターミナルAでは、これまで作ったPython APIを専用テーブルで起動します。

```sh
DYNAMODB_TABLE=sales-manager-test-day11-review .tools/uv/bin/uv run \
  --project apps/api --locked \
  sales-manager-api --env-file apps/api/.env.example
```

ターミナルBでは、Node.js 24.22.2が使える状態でNext.jsを起動します。

```sh
API_BASE_URL=http://127.0.0.1:8000 npm --prefix apps/web run dev -- --port 3000
```

API_BASE_URLはこのプロセスだけに渡し、既存の.env.localを書き換えません。.env.exampleは見本なので、自動では読み込まれない点にも注意します。

ブラウザーでhttp://127.0.0.1:3000を開きます。新しいテーブルなら空結果が表示され、手順書のコマンドで商品を登録して「最新の状態に更新」を押すと、商品名・コード・価格が表示されます。APIを止めて更新すると取得失敗、再起動して更新すると復帰します。

画面自体のHTTP 200と、商品取得の成功は別です。レビューでは画面内の状態も確認します。

## 今回の確認結果

```sh
npm --prefix apps/web run test
npm --prefix apps/web run lint
npm --prefix apps/web run typecheck
npm --prefix apps/web run build
```

Node標準テスト53件、Biome、TypeScript、本番ビルドが成功しました。テストには接続先・HTTPエラー・応答型・タイムアウトを含め、新しいテスト依存は追加していません。

隔離したChromeと架空APIで12項目を確認しました。読込中・空結果・503・不正なJSON・切断・タイムアウト・更新による復帰、ナビゲーション、404を確認し、1365pxと390pxの画面も目視しました。ブラウザーからPythonへ直接リクエストが出ないことも確認しています。

さらに実Python API・MiniStackで9項目。商品登録・更新の反映、無効商品の除外、保存先障害とhealthの違い、開発/本番サーバーを確認しました。確認専用テーブルとサーバーは片付け、もともと稼働していたMiniStackは保持しています。

詳細は[検証記録](https://github.com/hirolisberger/sales-manager-dashboard/blob/day11/docs/DAY11_REVIEW.md)へ残します。実AWS・認証・他OS/ブラウザー・支援技術・性能、予期しないサーバー例外を強制したerror.tsxの試験は未検証です。

## まとめと次回

画面からPython APIを読むための共通部分を作り、データがある場合も、空の場合も、失敗した場合も表示できるようになりました。ここからは、この枠と通信処理を使って業務操作を増やします。

Day 11の実装とこの記事はレビュー待ちです。承認・PRマージ・day11タグ登録後、別途の開始指示を受けてDay 12の商品管理画面へ進みます。Qiitaへの投稿は別に管理します。
