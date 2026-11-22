# Day 11：Next.jsの共通画面とAPI接続

実装・記事はレビュー待ち。[確認手順](DAY11_COMMANDS.md)、[検証記録](DAY11_REVIEW.md)、[API仕様](API_CONTRACT.md)を参照する。Next.js 16.4.6 / React 19.3.1 / TypeScript 6.0.3 / Node.js 24.22.2。新しい依存は追加していない。固定ロックの再導入時にnpm監査がNext.js 16.4.3の中程度指摘を報告したため、16.4.6へパッチ更新して関連依存のロックを更新した。更新後の監査は検出0件。実際の悪用可否を評価したという意味ではない。[公式リリース](https://github.com/vercel/next.js/releases/tag/v16.4.6)、[公式アドバイザリー例](https://github.com/vercel/next.js/security/advisories/GHSA-vvgp-ww4w-46vf)

## 今回の範囲

| URL | 表示と通信 |
| --- | --- |
| / | 共通レイアウトと有効商品の先頭3件。GET /products?is_active=true&limit=3 |
| /connection | Python APIの応答。GET /health |
| 存在しないURL | 共通レイアウト内の404 |

商品3件は一覧全体の総数や売上ではない。商品ID順の先頭を読み、続きがあれば案内だけを表示する。編集・登録・検索・ページ送りの管理画面はDay 12以降で追加する。認証済み表示や架空の集計値を出さない。APIのhealthは保存先を調べないため、接続確認成功と商品の取得成功は別の結果になる。

## Server / Clientの境界

ブラウザー → Next.jsサーバー → Python API → MiniStack。page.tsxからサーバー専用のlib/api.tsを呼ぶ。API_BASE_URLはNEXT_PUBLIC_を付けず、server-onlyのimportでClient Componentへの混入を防ぐ。ブラウザーはPythonやMiniStackへ直接接続しない。今回PythonのCORS設定や汎用転送APIは追加していない。

レイアウト・ページ・結果表示はServer Components。ナビゲーションの選択状態はusePathname、更新ボタンはrouter.refreshとuseTransitionを使うClient Components。error.tsxはNext.js 16.4.6のretryプロパティを使い、予期しない例外から再取得する。期待できる接続失敗はApiErrorの結果として表示し、例外の本文を画面へ渡さない。

## 接続設定と通信

API_BASE_URLは起動時のOS環境変数、またはapps/web/.env.localで指定する。.env.exampleは見本で自動読込されない。Day 11ではhttpのloopback（127.0.0.1 / localhost / ::1）のoriginだけを許可し、未設定・認証情報付き・パス・query・fragment・外部ホストは拒否する。失敗時の別接続先へのフォールバックはない。Docker間接続やAWS用originは配備時に別途設計・検証する。

lib/api-client.tsは固定した2種類のGETだけを提供する。cache: no-store、redirect: error、Accept: application/json、5秒のAbortSignal.timeoutを指定する。外部へのリダイレクトを追跡しない。JSONのContent-Typeと表示に使うデータの型・価格範囲・有効状態を実行時にも確認する。TypeScriptの型宣言だけで通信データが正しいとは扱わない。

各ページでconnection()を待ち、ビルド時にAPIへ接続しない。APIの準備がなくても本番ビルドを作り、リクエスト時に状態を取得する。SSRが必要な構成なので、このまま静的ファイルだけをS3へ置く方式にはしない。

## 画面の状態

| 状態 | 動作 |
| --- | --- |
| 取得中 | loading.tsxの「読み込み中です」。共通レイアウトを保持 |
| データあり | 商品名・コード・税込標準単価を表示 |
| データなし | 成功として「商品はまだ登録されていません」 |
| 接続/HTTP/JSON不整合/タイムアウト | 共通の取得失敗表示と更新ボタン |
| 更新中 | ボタンを無効化し「更新中…」 |
| 予期しない例外 | error.tsxの再試行UI |

エラー本文・接続先URL・例外詳細は画面へ出さない。X-Request-IDがUUIDなら確認用IDだけを表示する。更新ボタンは現在のページのServer Componentsを取り直す。Linkのprefetchを無効にし、未使用のページのAPI呼出しを先行させない。訪問済みのページへ戻るだけではルーター内に保持した表示を使う場合があるため、最新確認には更新ボタンを使う。

レイアウトはデスクトップのサイドバーと、640px以下の横ナビゲーション。本文へのスキップリンク、aria-current、表の見出し、キーボードのフォーカス表示、動きを減らす設定を用意した。390px/1365pxのChromeで確認したが、全ブラウザー・スクリーンリーダーの網羅検証ではない。

## 検証と限界

Node標準テスト53件、隔離Chrome+架空API12項目、実Python API+MiniStack9項目を確認。後者は専用テーブルと専用ポートを使い、既存データ・稼働サーバーを操作しない。Chrome確認は.env.localを書き換えず、子プロセスのAPI_BASE_URLを架空APIへ向ける。

React/Next.jsの境界、loading、connection、retry、環境変数はインストール済みNext.jsのnode_modules/next/dist/docs/と公式資料を2026-11-22に確認した。[Server / Client](https://nextjs.org/docs/app/getting-started/server-and-client-components)、[データ取得](https://nextjs.org/docs/app/getting-started/fetching-data)、[connection](https://nextjs.org/docs/app/api-reference/functions/connection)、[エラー処理](https://nextjs.org/docs/app/getting-started/error-handling)

未検証は認証・AWS配備・実AWSの応答制限と性能・他OS/ブラウザー・支援技術。予期しないサーバー例外を強制発生させたerror.tsxのブラウザー試験は未実施で、今回の障害試験は通常の接続失敗を対象にした。
