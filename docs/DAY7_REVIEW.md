# Day 7：商品マスタAPIの検証とレビュー

確認日：2026-10-30（Asia/Tokyo）。feature/day07、基点main/day06：`b92b01f71cc9125e3e7f15a4f19e6ad1b2bbc365`。Day 6の承認・[PR #5](https://github.com/hirolisberger/sales-manager-dashboard/pull/5)マージ・注釈付きday06タグとfetch後のmain一致を確認して着手。

**実装・記事・必要なローカル検証が完了し、Day 7はレビュー待ち。** Day 8は承認・mainマージと別途の開始指示まで進めない。

## 今回の実装と変更

- product_models.py：厳格な商品登録・部分更新と応答モデル。空・null・未知フィールド、価格・コード・名称の境界を検証。
- products.py：登録・詳細・一覧・更新/無効化。コード予約、条件付き版更新、最初の成功応答の永続化と再送。
- cursors.py：条件と店舗を結び付けた15分期限の商品カーソル。改ざん・期限・条件変更・再起動を拒否。
- product_routes.py / app.py：商品4操作を追加。local/test専用、同期SDK、クライアント終了、healthの通信不要を維持。
- errors.py：保存障害を503へ変換。503にRetry-Afterを付ける。入力・SDK本文は露出しない。
- [API仕様YAML](contracts/openapi.yaml)：説明文の実装範囲だけを更新。商品スキーマと全15操作の設計は維持。
- 単体テスト、[実MiniStack検証](../scripts/verify_day07_products.py)、[仕様](PRODUCT_API.md)、[全コマンドの解説](DAY7_COMMANDS.md)、[記事](../qiita/day07-product-master-api.md)。

既存仕様で必須の商品の要求キー・版条件・一覧継続をDay 7で実装した。売上側の再送・訂正・期間横断カーソルはDay 8〜10に残す。新しい依存は追加せず、ロック・SDK版・フロント・Compose・infraは変更していない。

## 単体テスト

```sh
UV_CACHE_DIR="$PWD/.cache/uv" .tools/uv/bin/uv run \
  --project apps/api --locked pytest apps/api/tests -q
```

**141 passed、警告なし。** Docker不要。商品HTTPテストの保存先はテストダブルで、DynamoDBの原子性の証明とは分ける。

| ファイル | 件数・内容 |
| --- | --- |
| test_product_models.py | 28：価格上下限・小数/bool/文字列/null、コード形式/長さ/改行、名称/Unicode、空PATCH・未知/変更不可項目・型変換の拒否 |
| test_products_api.py | 25：登録〜更新/無効化/再有効化、YAML応答照合、コード予約保持、再送と別内容409、404/412/版上限、必須/不正/重複ヘッダー、不正検索、JSON不正、ページング・空ページ・不一致商品の読み越し・署名/条件/期限/鍵/店舗、Query予算、競合、SDK障害503、awsモードのSDK生成前拒否 |
| test_api.py | 14：既存HTTP基盤。未実装ルートの例を/productsから/salesへ変更 |
| test_settings.py | 26：設定の優先順と境界 |
| test_aws.py | 3：SDKのローカル隔離と通信なしのAWS接続先確認 |
| test_repository.py | 22：DynamoDB要求・型・条件・容量・ページング・例外分類 |
| test_bootstrap.py | 18：初期化・seed・リセット・管理CLIの境界 |
| test_cli.py | 5：API CLIの待受条件・引数・設定エラー |

## 実MiniStackとの結合検証

```sh
UV_CACHE_DIR="$PWD/.cache/uv" .tools/uv/bin/uv run \
  --project apps/api --locked python scripts/verify_day07_products.py
```

**12項目成功、temporary_table_deleted=true。** HTTP部分はTestClientによるプロセス内処理、DBは実MiniStack。毎回一意名の専用テーブルだけを作成・削除する。

1. 登録・詳細・ETagとDBへの保存。
2. コード重複409と、商品が増えないこと。
3. 不正単価・UUID・不存在の拒否。
4. 更新・無効化・フィルターと予約コードの維持。
5. 後の変更があっても最初の201/200・本文・ETagを再送。
6. 古い版412・If-Match不足428で変更しない。
7. 有効商品のページングに重複・欠落なし、カーソル不正を拒否。
8. 同じコードの並行登録：201/409、1商品のみ。
9. 同じ要求の並行登録：両方201、同一商品、再送ヘッダー。
10. 同じ版の並行更新：200/412、版を1だけ増やす。
11. コード予約と最初の成功応答を強い整合性で読戻し。
12. 未作成テーブルの安全な503・Retry-After。

## 実サーバーと手順書

Uvicornを専用のloopbackポートで起動し、curlでhealth200・登録201・詳細200・無効化200・一覧絞り込み・古い版412・最初の応答の再送・DELETE405・SIGINT終了とポート閉鎖の9項目を確認した。

さらに [DAY7_COMMANDS.md](DAY7_COMMANDS.md) の手順3〜7を抽出し、専用サーバー・一時テーブルへ順に実行。登録の再送も加え、HTTPの201/200/412と保存後の商品version=3・600円・無効状態を照合した。URLのポートと確認用.cacheファイルの接頭辞だけを検証用へ置き換えた。カーソルのプレースホルダー例は置換が必要な説明用コマンドとして扱う。

確認用サーバーと一時テーブルは削除済み。既存MiniStackは着手時から起動済みだったため、コンテナ・ボリューム・既存テーブルを維持する。

## その他の検証

Ruff check / format --check（33ファイル）と、更新後YAMLの既存API仕様6グループが成功。uvロック整合性を確認。sdist / wheelを作成し、実行用依存だけの別venvへoffline導入、wheelに置換してソース外からアプリ・商品4操作・モデル・CLI helpを確認した。pytestなしで動作し、依存とロックは基点から不変。

公開Markdown35本・相対リンク199件・シェル101ブロック、表・フェンス・YAML/JSON・シェル構文を確認。実トークン一致検査と既知の個人情報パターンで検出なし。ローカル運用資料2本と認証ファイルのGit除外を確認。Day 0〜6の記事本文・既存データ例・Next.js・Compose・infraは不変。

## レビューで確認してほしいこと

1. [DAY7_COMMANDS.md](DAY7_COMMANDS.md)で登録・再送・詳細・更新・無効化・古い版の拒否を確認できること。
2. 同じ要求の再送と、新しい操作用の要求キーを区別できる説明になっていること。
3. 無効商品も参照でき、コードを別商品へ再利用できないこと。
4. 商品ページングは今回実装し、売上側の期間横断処理・認証・画面は後続Dayと区別していること。
5. 記事が実機検証とテストダブル・未検証範囲を区別していること。

## 未解決・公開・次のDay

実AWSの認証/IAM・配備・負荷性能、複数プロセスでのカーソル鍵共有、複数ページの同時更新スナップショットは未検証。ローカル鍵はAPI再起動で変わる。固定操作者local-adminは開発用で、本人認証ではない。商品APIはawsモードでは拒否し、認証前に公開運用しない。

Day 7公開予定は2026-12-07 JST、Qiita URL未取得。投稿・予約操作は行っていない。PRは従来どおりブラウザーで作成し、ユーザー承認後にmainマージとday07タグを行う。Day 8は未着手。
