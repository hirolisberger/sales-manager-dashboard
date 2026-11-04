# Day 8：売上登録・金額計算の検証とレビュー

確認日：2026-11-02（Asia/Tokyo）。feature/day08、基点main/day07：`3768214cac30e8ab1e81da7e5586959710a00f44`。Day 7の承認・[PR #6](https://github.com/hirolisberger/sales-manager-dashboard/pull/6)マージ・注釈付きday07タグとfetch後のmain一致を確認して着手。

**Day 8は実装・記事・ローカル検証を終え、2026-11-04にレビュー承認済み（対象a5b13c8）。** ブラウザーでのPR作成・mainマージ・day08タグ作成/pushは未実施。Day 9はmainマージ・タグpushと別途の開始指示を待つ。

## 変更内容と範囲

- sale_models.py：厳格な税込単価・数量・日付・UUID、未知項目拒否、1〜50明細と応答モデル。
- sales.py：整数計算、JST本日以前、商品スナップショット、売上/日付別/登録履歴/応答記録の一括保存、商品版と有効状態の条件確認、同じ要求の最初の201応答。
- sale_routes.py / app.py：local/test専用POST /sales。単一UUID要求ヘッダーはDay 7の共通関数を再利用。awsモードではSDK生成前に503。
- test_sales_api.py / verify_day08_sales.py：単体・HTTP・実MiniStackで正常系、境界、再送と競合を確認。
- [仕様](SALE_REGISTRATION.md)、[全コマンドの解説](DAY8_COMMANDS.md)、[記事](../qiita/day08-sales-registration-and-amount-calculation.md)。Day 7の完了記録も補完。

依存・ロック・Next.js・Compose・infra・Day 0〜7記事本文は変更しない。OpenAPIは実装範囲の説明のみ更新し、既存スキーマ・15操作の設計を維持。売上一覧/詳細はDay 9、訂正/取消はDay 10、認証はDay 19。

## pytest：197件

```sh
UV_CACHE_DIR="$PWD/.cache/uv" .tools/uv/bin/uv run \
  --project apps/api --locked pytest apps/api/tests -q
```

Day 8追加56件、既存141件が成功。追加項目は以下。

| 項目 | 確認内容 |
| --- | --- |
| 保存・応答 | Sale/Revisionが正本YAMLに一致、201・v1・要求ID、4項目と商品確認 |
| 型・範囲 | float/bool/文字列/null、単価・数量・日付・UUID、0/51明細、未知のサーバー項目 |
| 金額 | 実売価格を採用、0円・最大数量、上限ちょうどと1円超過 |
| 日付 | 不正日・閏日・過去日、日本時間0時直前/直後。固定時計を注入しOS時計は不変 |
| スナップショット | 登録時の商品名・実売価格、改名・無効化後の元応答 |
| 再送 | 同一要求、別本文、商品APIとのキー共有、同時作成、店舗/操作者境界 |
| 原子性・競合 | 商品変更・無効化・消失で全売上項目を拒否。保存競合・障害は503、内部情報は非表示 |
| API境界 | ヘッダー欠落/不正/重複、不正JSON、awsガードと非依存health、売上GET未実装 |

保存先は原子的操作を模したテストダブルで、DynamoDBの動作そのものの証明にはしない。既存の共通404試験で使っていた/salesはPOST追加により405になるため、未実装の/reports/salesへ対象を変更した。

## 実MiniStack：10項目

```sh
UV_CACHE_DIR="$PWD/.cache/uv" .tools/uv/bin/uv run \
  --project apps/api --locked python scripts/verify_day08_sales.py
```

1. 税込計算1,430円とCURRENT・日付別・版1履歴・応答記録の一致。新規キーは4件。
2. 改名・値上げ・無効化後も元の要求を同じ201応答で再送。新要求の無効商品は拒否。
3. 不正型・未来日・未知商品・不正明細の拒否と保存キー不変。
4. 9,999,999,999円の成功と、1円超過の拒否。
5. 読取後の実商品PATCHを挟み、実ConditionCheckで改名/無効化を拒否。売上4項目は保存されない。
6. 同一キーの並行2要求で1売上だけを確定。処理中503なら同じキーで再送して照合。
7. 異なるキーの並行2要求で異なる2売上を保存。
8. 100文字の補助平面Unicode名称を持つ50商品・50明細を54アクションで保存。
9. 注入した固定時計でJST0時直前/直後を検証。
10. APIアプリを作り直してもDynamoDBの元応答を再送。

HTTPはTestClient、DBは127.0.0.1:4566の実MiniStack。毎回一意名sales-manager-test-day08-*を作成し、成功・失敗時とも自身のテーブルを削除する。既存のsales-manager-localやS3/Cognitoは変更しない。check_count=10・temporary_table_deleted=trueを確認。

## 実Uvicornと手順書

専用テーブルsales-manager-test-day08-live-*と空きポートに実APIを起動し、9項目を確認。

- health200、確認用商品201、売上201・合計1,100円、同じ要求201・同じ応答。
- 手順書のSDK読取でCURRENT・日付別・履歴の一致。
- 小数数量422、同じキーの本文変更409、売上GET/詳細未実装の405/404。
- Ctrl+C相当で終了コード0、ポート閉鎖。

[DAY8_COMMANDS.md](DAY8_COMMANDS.md)の手順3〜6の4シェルブロックを抽出して実行。置換したのはURLの空きポートと検証用.cacheファイル名だけ。実機検証は既存データを使わず、専用サーバーとテーブルを削除・停止した。

## 静的・仕様・配布・文書の確認

Ruff checkとformat --check（38ファイル）、既存API仕様の6グループが成功。実行依存だけを空のvenvへ固定ロックからoffline導入し、sdist/wheelを作成・wheelへ入れ替え、ソース外から売上モデル・計算・アプリ構築・CLI helpを確認した。依存・ロックは変更していない。

公開Markdown39本・相対リンク222件・シェル112ブロック、表・フェンス・YAML/JSON・シェル構文を確認。実トークン一致検査と既知パターンで検出なし、ローカル運用資料2本と認証ファイルのGit除外を確認。Day 0〜7の記事・既存データ例・Next.js・Compose・infraは不変。今回起動したMiniStackは通常のdownで停止し、名前付きボリュームは保持する。

## レビューで確認してほしいこと

1. 手順書どおりに550円×2＝1,100円を登録・再送・保存内容確認できる。
2. 税込整数円・整数数量・過去日と未来日の扱いが要件に合う。
3. 商品標準価格と実売価格、登録時の商品名を区別する説明が伝わる。
4. 同じ要求を再送する場合と別売上を登録する場合のキーの使い分けが明確。
5. 今回は売上登録だけで、一覧・詳細・訂正・認証を完成済みと扱っていない。

## 未検証・公開・次のDay

実AWS/IAM/配備、負荷・容量性能、他環境の互換性、売上検索・訂正・取消・集計・画面・認証は未検証または後続Day。固定操作者は開発用で、未認証の売上APIを公開運用しない。

Day 8公開予定は2026-12-08 JST、Qiita URL未取得。レビューは2026-11-04に承認済み。PRは従来どおりブラウザーで作成し、Create a merge commitでmainへマージする。そのマージコミットへday08注釈付きタグを作成・pushし、feature/day08は保持する。Day 9はmainマージ・タグpushと別途の開始指示まで着手しない。Qiita操作は行っていない。

## レビュー提出対象

実装・API仕様・記事の承認対象コミットは`a5b13c8ae63a5cac60a0379070b513a12c2cf51b`。初回提出`4e158489e9674c673f9c92a30f9460792814f4e4`は対象を記録した本節だけの追加。承認後の提出更新は承認・次回条件の記録だけとし、実装・API仕様・記事内コマンドは変更しない。

## ユーザーのレビュー承認

2026-11-04（Asia/Tokyo）、ユーザーの「day8のレビューOKです。」をDay 8のレビュー承認として記録。承認対象は上記a5b13c8で、実装・API仕様・記事を含む。

承認記録の更新前にfetchし、feature先端4e15848・origin/feature/day08の一致とmain/day07 3768214を確認。GitHub公開APIでmain向けPRは未作成。承認・次回条件の記録だけを更新してfeature/day08へpushし、ブラウザーでのPR作成・マージ用の本文を用意する。機能変更がないため機能テストは再実行せず、文書検証と承認対象からのコード・API仕様・コマンドの不変を確認する。
