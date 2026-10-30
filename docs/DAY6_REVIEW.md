# Day 6：MiniStackへの保存・初期データ・リセット

確認日：2026-10-30（Asia/Tokyo）。`feature/day06`、基点main/day05は`2a1354f832dc0f4df8356ea5e328e9bdb7c162b5`。Day 5の承認・[PR #4](https://github.com/hirolisberger/sales-manager-dashboard/pull/4)マージ・注釈付きday05タグ、fetch後のmain一致を確認して着手。

**実装・記事・必要なローカル検証が完了し、2026-10-30にDay 6はレビュー承認済み。** 承認対象は`c5d4c9df23b8ca426fbeb450042752b146ed9190`。PR作成・mainマージ・day06タグは未完了。Day 7はmainマージと別途の開始指示を受けるまで進めない。

## 今回の実装とレビュー対象

- `apps/api/src/sales_manager_api/aws.py`：SDKのローカル/AWS境界、個人資格情報の隔離。
- `repository.py`：店舗内のキー、強い整合性のGetItem / Query、条件付きトランザクション、整数・容量ガード、SDK例外の分類。
- `bootstrap.py` / `data_cli.py`：init / seed / inspect / reset。既存構成・データの確認、再投入による上書き拒否。
- `settings.py` / `.env.example`：DYNAMODB_TABLE / STORE_ID。API実行依存とロックへBoto3 / botocore 1.43.121を追加。
- 単体テストと`scripts/verify_day06_persistence.py`：実アプリの保存層をMiniStackで確認。
- [保存仕様](PERSISTENCE.md)、[全コマンドと各指定の意味](DAY6_COMMANDS.md)、[記事](../qiita/day06-ministack-persistence-and-seed-data.md)。README・開発ルール・計画・Day 5完了記録の補完。

商品・売上のHTTP API、認証・HTTPの冪等性・署名付きカーソル・売上のトランザクション計画は今回の実装に含めない。実装済みHTTPルートはhealthだけ。OpenAPI正本は変更していない。

## テストの内容

| 分類 | 確認した内容 |
| --- | --- |
| 設定 | Day 5の優先順位・URL等に加え、テーブル名と店舗IDの不正値 |
| SDK境界 | 不正な個人profile/設定ファイル・ダミーの個人資格情報・別エンドポイント・プロキシがあってもダミー資格情報とloopbackを使う。設定ファイル読込・資格情報探索・外部通信を阻止するテスト。OS環境の不変 |
| AWS用クライアント | ダミー資格情報で生成し、標準エンドポイントを確認。ネットワークは阻止。AWSへの動作検証ではない |
| 保存・取得 | SDK Stubberによる実際の要求形式、強い整合性、整数・bool・入れ子、未存在のNone |
| 入力・容量 | float / Decimal / set / bytes / 不正辞書キー、保存済み小数、件数・重複項目・項目/要求サイズを拒否 |
| Query | 継続キー付き空ページ、次ページ、並び順、他店舗・別検索のキーと不正Limitの拒否 |
| 条件と障害 | Put / Delete / ConditionCheck、条件失敗と容量/権限/理由不明のSDK障害を分ける。例外にSDK本文を露出しない |
| 初期化 | 既存構成の照合、作成、構成不一致で変更しない、seedの原子性・再実行・部分データ/変更済みデータの拒否、同一seedの競合 |
| 管理CLI | AWSモード・無関係な名前・誤確認名をSDK生成前に拒否。正しいテーブルだけのリセット、終了コードと例外の匿名化 |
| 既存基盤 | Day 5のhealth / HTTPエラー・要求ID・ログ・CLIの39件を含む |

```sh
UV_CACHE_DIR="$PWD/.cache/uv" .tools/uv/bin/uv run \
  --project apps/api --locked pytest apps/api/tests -q
```

**88 passed、警告なし**。単体テストはDocker不要で、実AWSへの通信を行わない。

| テストファイル | 件数 |
| --- | --- |
| test_settings.py | 26 |
| test_aws.py | 3 |
| test_repository.py | 22 |
| test_bootstrap.py | 18 |
| test_api.py | 14 |
| test_cli.py | 5 |

## MiniStackでの実機確認

```sh
docker compose --env-file /dev/null -f compose.yaml up -d --wait

UV_CACHE_DIR="$PWD/.cache/uv" .tools/uv/bin/uv run \
  --project apps/api --locked python scripts/verify_day06_persistence.py
```

10項目成功：テーブル再初期化、原子的seed・再投入、整数/bool読戻し、ページング、店舗の分離、コード予約競合の全体ロールバック、更新と古い版条件の拒否、変更済みseed拒否、誤リセット名拒否、空へリセットして再投入。

専用一時テーブルを使用し、既存のアプリ用テーブルやDay 3の他データを変更しない。検証後は自身で作成したテーブルを削除する。

追加確認：実CLIでinit初回/再実行・seed初回/再実行・商品2件参照・reset後0件・再seed・誤確認名の終了コード2、計9期待値を確認。別の専用テーブルを削除済み。

再起動確認用に成功した検証テーブルを一時保持し、restart後とdown / up後に5項目を再取得。両方とも内容のSHA-256が一致した。保持は既存Composeの名前付きボリュームによる。検証テーブルは削除済みで、Composeも通常のdownで停止済み。既存ボリュームは保持した。

## 静的検証と再導入

- Ruff check / format --check：成功。対象apps/apiとscripts。
- Day 4のAPI仕様検証：6グループ成功。YAML正本・架空の売上データは変更なし。
- uv.lockの固定再導入：実行用依存のみの別venvをoffline作成。sdist / wheel作成成功、wheelへ置換後にソース外から読込・CLI help・固定データ5件を確認。pytestなしで利用でき、ロックのSHA-256は不変。
- 公開Markdown31本・相対リンク170件・シェル85ブロック、フェンス・表・YAML/JSON・シェル構文を確認。実トークンの一致検査と既知の個人情報パターンで検出なし。ローカル運用資料2本と認証ファイルのGit除外を確認。
- Next.js・Compose・infra・OpenAPI正本・架空の売上データ・Day 0〜5の記事本文は基点から不変。Day 5確認記録の変更は完了状態の補完のみ。

## レビューで確認してほしいこと

1. [DAY6_COMMANDS.md](DAY6_COMMANDS.md)のinit / seed / inspectで、商品2件を確認できること。
2. 再実行でcreated / seededがfalseになり、データを増やさないこと。
3. resetは対象テーブルの全店舗・全項目を消す操作で、通常の停止や再初期化と区別されていること。
4. 型・条件・容量・接続先のガードを保存層へ集め、業務ルールやHTTP APIの完成と混同していないこと。
5. 記事が今回の実装・実測範囲と未検証のAWS範囲を区別していること。

## 未解決・後続Day

実AWSのIAM・配備・容量/性能・異なる環境での動作は未検証。複数ページの同時更新スナップショットは保証しない。SDKの試行は1回で、通信結果不明時の業務再送は後続Dayで扱う。商品登録の業務検証・APIはDay 7、売上と履歴・再送はDay 8〜10、S3はDay 17、認証はDay 19。

Day 6の公開予定は2026-12-06 JST、記事URL未取得。Qiitaへの投稿・予約操作は未実施。PRは従来どおりブラウザーで作成し、承認後にmainへマージしてday06タグを作成する。Day 7は未着手。

## レビュー提出対象

実装・設定・依存・記事の対象コミットは`c5d4c9df23b8ca426fbeb450042752b146ed9190`。この対象を記録する提出コミットは、本節だけの追加とする。feature/day06をpushし、従来どおりブラウザーでmain向けPRを作成する。レビュー承認前にはマージ・day06タグ作成を行わない。

## 2026-10-30：ユーザーレビュー承認

ユーザーの「Day6のレビュー完了とします」をDay 6全体のレビュー承認として記録する。承認対象は`c5d4c9df23b8ca426fbeb450042752b146ed9190`。承認後は状態・提出・次回条件の記録だけを更新し、実装・API仕様・設定・依存・記事内の実行コマンドは変更していない。

公開APIでPR未作成を確認した。従来どおりブラウザーでmain向けPRを作成し、Create a merge commitでマージする。feature/day06は保持し、実際のマージコミットに注釈付きday06タグを作成・pushする。Day 7開始とQiita操作は別の指示を待つ。
