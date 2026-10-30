# Day 4：データモデル・API契約の検証とレビュー

確認日：2026-10-30（Asia/Tokyo）。ブランチ`feature/day04`、基点main / day03：`9cb473ddf23673b3d474537e18ce259f05547c7e`。Day 3はユーザー承認済みで、[PR #2](https://github.com/hirolisberger/sales-manager-dashboard/pull/2)のマージ・day03タグを確認して着手した。

**設計・検証スクリプト・記事は実装完了、ユーザーレビュー待ち。** 本API・製品用保存層は未実装。Day 4の承認・PRマージと別途の開始指示を受けるまでDay 5へ進まない。

## 成果物

- [DATA_MODEL.md](DATA_MODEL.md)：データ項目、単一テーブルのキー、検索・集計・訂正・再送、制限。
- [API_CONTRACT.md](API_CONTRACT.md)と[OpenAPI](contracts/openapi.json)：15操作、厳格な入力、ETag・要求キー、エラー、将来のCSV契約。
- [架空データ](examples/day04-fixtures.json)：Day 1と同じ売上・期待値、固定の架空時計。
- `scripts/day04_design.py`：設計例の参照計算とトランザクション構成。アプリからはimportしない。
- `scripts/verify_day04_contract.py`：文書契約と業務例の検証。
- `scripts/verify_day04_dynamodb.py`：MiniStackの一時テーブルで保存・競合・ページングを検証。
- `infra/local-aws/pyproject.toml`と`uv.lock`：任意のcontractsグループ。jsonschema 4.26.0、openapi-spec-validator 0.9.0を固定。
- [Day 4記事](../qiita/day04-data-model-and-api-contract.md)、README・計画・開発ルール・導線の更新。Day 3確認記録のPR/タグ情報だけを補完。

## 再現手順

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
- Day 4はレビュー未承認。PRは既定どおりブラウザーで作成・マージする。実際のPR URLは作成後に記録する。mainマージ・day04タグ・Day 5・Qiita操作は未実施。
- Qiita公開予定は2026-12-04（JST）。開発・レビュー・公開の状態は別々に管理する。
