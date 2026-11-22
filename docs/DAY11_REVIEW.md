# Day 11：共通画面とPython API接続の検証・レビュー

確認日2026-11-22（Asia/Tokyo）。feature/day11の基点はmain/day10の6196a4eb6cea52c063939df9e27facac3e8d7d1b。ユーザーのDay 10レビュー承認・次の記事作成指示を受け、PR #9のマージとday10タグのpushを確認して着手した。

**Day 11は実装・記事・検証完了、レビュー待ち。** 承認前にmainへマージせず、Day 12は承認・PRマージと別途の開始指示を待つ。Qiita操作は行っていない。

## 変更ファイルと範囲

- apps/web/src/app/：共通レイアウト、ホームの商品3件参照、接続確認、loading/error/404、レスポンシブCSS。
- apps/web/src/components/：ナビゲーション・再取得・接続エラー。
- apps/web/src/lib/：サーバー専用入口と型検証付きの固定GETクライアント。
- apps/web/tests/api-client.test.ts：Node標準の単体テスト。
- apps/web/package.json・tsconfig.json・biome.json・.env.example：ES Modules、test script、検査範囲、環境変数見本。
- apps/web/package-lock.json：Next.jsのセキュリティパッチに対応した固定ロック。
- scripts/verify_day11_web.mjs：隔離Chrome・本番Next.js・架空API。
- scripts/verify_day11_live.py：専用テーブル・実Python API・MiniStack・Next.js。
- [仕様](WEB_FOUNDATION.md)、[全コマンド解説](DAY11_COMMANDS.md)、[記事](../qiita/day11-nextjs-layout-and-api-client.md)、webのREADMEと概要・進行記録。

Python実装・Python依存/ロック・API仕様YAML・保存データ例・Compose・infra・Day 0〜10記事本文は不変。Day 10のPR #9とday10タグ完了情報はこのブランチで補完し、共有済みタグとfeature/day10を変更しない。

## Next.jsのパッチ更新と再導入

固定依存の再導入時にnpm監査がNext.js 16.4.3へ中程度1パッケージ（複数のアドバイザリー）の指摘を報告した。公式リリース・アドバイザリーとnpmの修正可能版を確認し、Next.jsを16.4.6へ完全固定で更新した。関連する@next/env・各プラットフォーム用SWCのロックも更新。React 19.3.1など他の直接依存は維持し、新しい依存は追加していない。

更新後のnpm auditは検出0件。更新後のロックからnpm ci --offlineを実行し、ロックのSHA256不変、Nodeテスト・Biome・TypeScript・本番ビルドを確認した。API_BASE_URLを未稼働のloopbackポートへ向けてもビルドが成功し、ビルド時のAPI接続を不要にしている。

監査は2026-11-22時点の結果で、実際の悪用可否や将来の安全性を保証しない。[公式リリース](https://github.com/vercel/next.js/releases/tag/v16.4.6)、[公式アドバイザリー例](https://github.com/vercel/next.js/security/advisories/GHSA-vvgp-ww4w-46vf)

## 単体テスト：53件

```sh
npm --prefix apps/web run test
npm --prefix apps/web run lint
npm --prefix apps/web run typecheck
npm --prefix apps/web run build
```

| 対象 | 確認内容 |
| --- | --- |
| 接続設定 | 未設定・外部/不正origin・URL内資格情報・query/path/fragmentを拒否。loopbackを許可 |
| リクエスト | 固定GET、Accept、no-store、リダイレクト拒否、タイムアウトのsignal |
| 応答 | health、商品3件、空結果、価格/名前/UUID/有効状態とページ形状の型検証 |
| 失敗 | 主な4xx/5xx、JSON以外・不正JSON、切断、タイムアウト |
| 公開情報 | 例外/本文を隠し、UUIDの要求IDだけを保持 |

単体テストはfetchのテストダブル。DOMや実ネットワークの検証と区別する。Node.js標準で実行し、追加のテストフレームワークを導入しない。Biome対象17ファイル、TypeScript、本番ビルドが成功。

## 実ブラウザー：12項目

```sh
node scripts/verify_day11_web.mjs
```

1. ホームの商品3件・円表示・選択中ナビ。
2. Link経由のページ遷移とAPI接続確認。
3. 商品0件を通信成功の空結果として表示。
4. 503は共通メッセージと要求ID、内部本文なし。
5. 更新ボタンで新しい取得が行われ、障害から復帰。
6. 不正なJSON形状でも内部本文を出さない。
7. 接続切断の取得失敗。
8. 5秒タイムアウトの取得失敗。
9. 1.8秒遅延でloading表示→成功へ切替。
10. 幅390pxでページ全体が横にはみ出さない。1365px/390pxの画像を目視確認。
11. 未知URLは共通枠とHTTP 404。
12. ブラウザーから架空Python APIへの直接通信なし、JavaScript例外なし。

本番Next.js・架空API・Chromeの一時プロファイルと専用ポートを使った。結果と画像は.cache/day11-web/。普段のブラウザープロファイルや.env.localは変更せず、専用サーバー・Chromeを終了し一時プロファイルを削除した。

## 実Python API・MiniStack：9項目

```sh
UV_CACHE_DIR="$PWD/.cache/uv" .tools/uv/bin/uv run \
  --project apps/api --locked python scripts/verify_day11_live.py
```

1. 専用テーブルの空結果が本番画面に表示される。
2. 実APIで商品登録し、先頭3件と続きの案内を表示。
3. マスタ改名・600円への変更が新しいサーバー描画に反映される。
4. 無効商品を表示しない。
5. 実Python APIのhealthを接続確認に表示。
6. 専用テーブル削除後は商品取得失敗でもhealthは成功する。
7. 専用Python API停止後は接続確認も失敗する。
8. 本番サーバーの未知URLが404。
9. 開発サーバーでも共通枠と取得失敗を表示。

手順書5の商品登録シェルブロックを抽出し、APIポートと.cache保存先だけ置き換えて実行した。201を3回確認。別に4件目を登録して件数上限を検証。一意名sales-manager-test-day11-*だけを作成し、成功・失敗時とも自身のテーブルとAPI/Next.jsを片付けた。既存の稼働MiniStack・名前付きボリューム・既存テーブル・S3/Cognitoは保持した。

## 追加の静的・文書確認

PythonのRuff check / format --check（45ファイル）、ブラウザー試験のnode --checkを実施。API仕様とPython実装は不変なので、Day 10の330件と仕様6群を今回の再実行件数には含めない。実APIとの結合を上記9項目で確認した。

ブラウザー向け生成JSにAPI_BASE_URLや接続先の固定文字列を含まないことを確認した。公開Markdown52本・相対リンク299件・シェル157ブロック、表/フェンス/YAML/JSON/シェル構文、実トークン一致検査・既知の個人情報パターンで検出なし、ローカル運用資料2本と認証ファイルのGit除外を確認した。今回の公開ファイルの検査で、過去履歴全体の再監査ではない。

## レビューで確認してほしいこと

1. [手順書](DAY11_COMMANDS.md)どおり別ターミナルでAPIと画面を起動できる。
2. 共通ナビ・ホーム・接続確認を使え、商品名・コード・価格が表示される。
3. API停止→更新→失敗、API再起動→更新→復帰を確認できる。
4. データ0件と通信失敗、healthと保存先の状態の違いが伝わる。
5. モバイル幅・読込中・更新ボタン、[記事](../qiita/day11-nextjs-layout-and-api-client.md)とコマンドの説明が用途に合う。

## 未検証・公開・次のDay

実AWS・認証・他OS/ブラウザー・スクリーンリーダー・性能/配備制限は未検証。予期しないサーバー例外を強制したerror.tsxのブラウザー試験は未実施。通常の接続失敗は上記で確認。商品編集・売上入力・集計は後続Day。

公開予定2026-12-11 JST、Qiita URL未取得。feature/day11をpushし、PRは既定どおりブラウザーで作成する。承認後にCreate a merge commitでmainへマージし、マージコミットにday11注釈付きタグを作成・pushする。feature/day11を保持。**Day 12へはまだ進めない。**

## レビュー提出対象

実装・設定・ロック・記事のレビュー対象コミットは5779b02628515239913d8186b662db21fb7f8d4a。この対象を記録する提出コミットは本節だけの追加とする。feature/day11をpushし、PRは既定どおりブラウザーで作成する。承認前にmainマージ・day11タグ作成・Day 12開始を行わない。
