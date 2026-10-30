# Day 4：データモデル・API契約の検証とレビュー

確認日：2026-10-30（Asia/Tokyo）。ブランチ`feature/day04`、基点main / day03：`9cb473ddf23673b3d474537e18ce259f05547c7e`。Day 3はユーザー承認済みで、[PR #2](https://github.com/hirolisberger/sales-manager-dashboard/pull/2)のマージ・day03タグを確認して着手した。

**設計・検証スクリプト・記事は実装完了、2026-10-30にユーザーレビュー承認済み。** 承認対象は`21307cc248fe0cb5ebd7220f21cd1b3eb733c2ec`。本API・製品用保存層は未実装。ブラウザーでのPR作成・mainマージとday04タグ作成は未完了。PRマージと別途の開始指示を受けるまでDay 5へ進まない。

## 成果物

- [DATA_MODEL.md](DATA_MODEL.md)：データ項目、単一テーブルのキー、検索・集計・訂正・再送、制限。
- [API_CONTRACT.md](API_CONTRACT.md)と[OpenAPI YAML](contracts/openapi.yaml)：15操作、厳格な入力、ETag・要求キー、エラー、将来のCSV契約。
- [架空データ](examples/day04-fixtures.json)：Day 1と同じ売上・期待値、固定の架空時計。
- `scripts/day04_design.py`：設計例の参照計算とトランザクション構成。アプリからはimportしない。
- `scripts/verify_day04_contract.py`：文書契約と業務例の検証。
- `scripts/verify_day04_dynamodb.py`：MiniStackの一時テーブルで保存・競合・ページングを検証。
- `infra/local-aws/pyproject.toml`と`uv.lock`：任意のcontractsグループ。jsonschema 4.26.0、openapi-spec-validator 0.9.0、PyYAML 6.0.3を固定。
- [Day 4記事](../qiita/day04-data-model-and-api-contract.md)、README・計画・開発ルール・導線の更新。Day 3確認記録のPR/タグ情報だけを補完。

## 再現手順

コマンド・各オプションの意味、仮想環境、変更が残る場所は [DAY4_COMMANDS.md](DAY4_COMMANDS.md) に一つずつ説明する。

macOS ARM64、Python 3.14.9、uv 0.13.6、Docker 29.1.2、MiniStack 1.5.33。プロジェクトルートで実行する。依存は専用の`infra/local-aws/.venv`に入る。

```sh
UV_CACHE_DIR="$PWD/.cache/uv" .tools/uv/bin/uv sync \
  --project infra/local-aws --group contracts --locked

UV_CACHE_DIR="$PWD/.cache/uv" .tools/uv/bin/uv run \
  --project infra/local-aws --group contracts --locked \
  python scripts/verify_day04_contract.py

docker compose --env-file /dev/null -f compose.yaml up -d --wait --wait-timeout 90

UV_CACHE_DIR="$PWD/.cache/uv" .tools/uv/bin/uv run \
  --project infra/local-aws --group contracts --locked \
  python scripts/verify_day04_dynamodb.py

docker compose --env-file /dev/null -f compose.yaml down
```

グローバルのuvを使う場合は`.tools/uv/bin/uv`を`uv`へ置き換える。実AWS、LocalStackの認証ファイル、個人のAWS設定は使わない。スクリプトは`day04-design-`から始まる一意名のテーブルだけを作成しfinallyで削除する。強制終了時の残存は別途確認が必要。名前付きボリュームは維持する。

## 確認結果

| 確認 | 結果 |
| --- | --- |
| OpenAPI | 3.1.0の文書を公式仕様対応バリデーターで検証。15操作とoperationId一意、更新ヘッダーの指定を確認 |
| 入力の拒否 | bool・小数1.0・数値文字列・負価格・数量0・上限超過・51件超・未知フィールド・存在しない日付・空理由を拒否 |
| 応答例 | 商品・売上・履歴・共通エラー・0件集計・受付中CSVジョブのスキーマ一致 |
| スナップショット | マスタの名称・価格・有効状態を変えても旧明細の値を保持。無効商品の新規選択・明示再取得を拒否 |
| 訂正条件 | 未知/重複明細ID・取消済みの訂正・未来日を拒否。期間逆転・367日を拒否、閏年366日を許可 |
| 金額・CSV | 2,640→2,090→1,430円、紅茶330円、有効3明細・数量3・売上2件。CSVへ書出し/再読込して金額一致 |
| 日付 | UTC/JSTの境界一致。別月訂正後、12月550円・1月880円 |
| 保存上限の例 | 50種類・50明細・100文字の補助平面Unicode名称で、最大55アクション、最大項目153,333 bytes、要求JSON400,589 bytes（fixtureテーブル名） |
| 契約検証の実行 | `verify_day04_contract.py`：6テストグループ成功 |
| MiniStack・重複と原子性 | 商品コード競合で新商品が残らない。売上・履歴・参照・要求記録の一括保存と、重複要求キーによる全体ロールバックが成功 |
| MiniStack・再送記録 | 最新880円への訂正後も、最初の応答1,430円・ETag v1を保持 |
| MiniStack・商品競合 | 読取後の無効化/版変更で売上登録全体を拒否し、最新版・要求記録が残らない |
| MiniStack・ページング | Limit=1のフィルター後空ページとLastEvaluatedKeyを再現。続行後に有効な売上を取得 |
| MiniStack・訂正と取消 | 最新版・日付別参照・版1〜3の変更前後履歴が一致。取消除外、商品別選択、別月移動、古い版の更新拒否と部分保存なし |
| MiniStack・最大件数例 | 異なる50商品のConditionCheckを含む54アクション登録、55アクション別日訂正が成功 |
| MiniStack実行・削除 | `verify_day04_dynamodb.py`：10確認項目成功、検証用テーブル削除を確認 |
| ロック再現性 | 空の別仮想環境へcontracts込みでlocked/offline導入・import成功。uv.lockのSHA-256が再導入前後で一致 |
| 静的検証 | scriptsのRuff check成功、6ファイルのformat --check成功 |
| 文書と匿名化 | 公開Markdown22本、相対リンク101件、シェル50ブロックの構文・フェンス・JSONを確認。実トークン混入なし、個人用2資料と認証ファイルはGit除外・未追跡 |
| 既存成果物 | apps、.nvmrc、compose.yaml、Day 3の接続ヘルパーはday03と差分なし。アプリビルド・Day 3ベンチマークの再実行は省略 |
| 後片付け | 最終10項目検証後の一時テーブル削除とCompose down成功。名前付きボリュームを保持 |

静的検証は既存のRuffを使う。

```sh
UV_CACHE_DIR="$PWD/.cache/uv" .tools/uv/bin/uv run \
  --project apps/api --locked ruff check \
  --config infra/local-aws/pyproject.toml scripts

UV_CACHE_DIR="$PWD/.cache/uv" .tools/uv/bin/uv run \
  --project apps/api --locked ruff format --check \
  --config infra/local-aws/pyproject.toml scripts
```

## レビューしてほしいこと

1. 単価・数量・50明細の上限と、取引時の値を保持する訂正仕様。
2. 単一テーブル、日付別参照の複製、最大55アクションと容量ガード。
3. 期間・商品フィルター、売上件数と明細数の違い、取消除外・CSV一致。
4. If-Matchと要求キーを併用し、再送には初回応答を返す方針。
5. 366日検索のコスト、同時更新時のスナップショットを保証しない範囲、後続Dayの検証計画。
6. 記事が設計検証と実際に動作するAPIを区別し、未作成day04タグを完成済みとしていないこと。

## 未実装・未検証と次の条件

- HTTP API、認証・権限、HTTP経由の整数検証・If-Match・再送の実装は未着手。スクリプトの要求キーは設計例のラベルで、HTTPのUUID入力検証を代替しない。
- カーソルのHMAC・期限・ページ間の同時更新、0補完の実集計API、CSVジョブ/署名URLは後続Day。
- 366日・大量売上の実用性能、料金、事前集計、DynamoDB厳密サイズ・実AWSの挙動、障害注入・並行負荷は未検証。
- 参照スクリプトは固定の時計・店舗・明細ID生成を使う。製品コードへそのまま移植しない。
- 認証ファイルと個人用運用資料はGit対象外を維持。過去コミットの履歴書き換えはしていない。
- Day 4は2026-10-30にレビュー承認済み。公開APIでPR未作成を確認した。PRは既定どおりブラウザーで作成・マージし、実URLを記録する。mainマージ・day04タグ・Day 5・Qiita操作は未実施。
- Qiita公開予定は2026-12-04（JST）。開発・レビュー・公開の状態は別々に管理する。

## 提出記録

初回のレビュー対象の設計・コード・記事は `79f750f0fdbb7297669177d85a12152f9552f78f`。その直後の提出記録コミットは本節のみの追加だった。コマンド解説とYAML化を含む最新対象`21307cc248fe0cb5ebd7220f21cd1b3eb733c2ec`が2026-10-30に承認された。提出先はfeature/day04で、PRはユーザーがブラウザーで作成する。PR作成後に実URLを記録する。

## 2026-10-30：手元の動作確認とコマンド解説

ユーザーから「動作確認ができました」と報告を受けた。実行出力は未受領で、レビュー承認とは別に記録する。続く質問を受け [DAY4_COMMANDS.md](DAY4_COMMANDS.md) に5コマンドと各指定の解説を追加し、記事と本記録からリンクした。設計・検証コード・依存・記事内の実行コマンドは変更していない。

追加文書の確認：公開Markdown23本・相対リンク114件・シェル56ブロックの構文、表・フェンス、匿名化と実トークン混入なしを確認。既存記事/本記録の実行コードブロックと、設計・アプリ・検証コード・依存・Composeに差分なし。文書の追加のため機能テストやコンテナの再起動は行っていない。

## 2026-10-30：OpenAPIの正本をYAMLへ統一

ユーザーの依頼により契約の正本を`docs/contracts/openapi.yaml`へ統一し、JSON版を削除した。検証スクリプトはPyYAML 6.0.3の`safe_load`で読み込む。PyYAMLは既存の間接依存と同じバージョンをcontractsグループの直接依存として宣言し、ロックも更新した。AGENTS・API契約・コマンド解説・記事の形式説明と参照先を合わせた。

| 今回の確認 | 結果 |
| --- | --- |
| 定義内容の同一性 | 変換前JSONと変換後YAMLを読み込んだ全内容が一致。正規化JSONでも比較し、文字列・数値・bool・nullの型が保持されることを確認 |
| HTTP応答コード | 15操作のresponsesキーが文字列であることを確認。`'null'`などの型名も文字列として保持 |
| 契約検証 | YAMLを読んで`verify_day04_contract.py`の6テストグループが成功。既存の実行コマンドは不変 |
| 依存の固定 | 空の別venvへcontracts込みのlocked/offline導入とimportが成功。ロックのSHA-256が再導入前後で一致し、全パッケージのバージョンは変更前と同じ |
| 静的検証 | scriptsのRuff check成功、6ファイルのformat --check成功 |
| 文書・公開範囲 | Markdown23本・相対リンク115件・シェル56ブロック、表・フェンスと匿名化、実トークン混入なしを確認。公開対象に旧OpenAPIファイルパスの参照は残っていない |

APIや保存処理の契約内容は変更していない。DynamoDB検証スクリプト・アプリ・Composeも変更していないため、MiniStackの再起動・保存検証の再実行は行わず、初回の10項目成功とユーザーの動作確認報告を保持する。この修正の提出時点ではDay 4をレビュー待ちとした。

## 2026-10-30：ユーザーレビュー承認

ユーザーの「day4のレビュー完了です。」をDay 4全体のレビュー承認として記録する。承認対象は`21307cc248fe0cb5ebd7220f21cd1b3eb733c2ec`。承認後は状態・提出・次のDayの条件だけを更新し、設計の内容・コード・設定・依存・記事内の実行コマンドは変更していない。

PRは公開API確認時点で未作成。ブラウザーでmain向けPRを作成し、Create a merge commitでマージする。feature/day04は保持する。マージ後は実際のマージコミットへ注釈付きday04タグを作成・pushする。Day 5の開始とQiita操作は別の指示を待つ。
