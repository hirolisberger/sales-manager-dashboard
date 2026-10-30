# Day 6：保存・初期データ・リセットの確認コマンド

すべてプロジェクトルート`sales-manager-dashboard/`で実行する。Python 3.14.9、uv 0.13.6、Docker ComposeとDay 3の固定MiniStackを使う。uvは今回`.tools/uv/bin/uv`に配置している。別の場所へ導入した読者は、その部分を自身の`uv`へ置き換える。

Python環境は`apps/api/.venv/`。uvが作成・選択するため、手動のvenv作成・activateは不要。個人のAWS認証情報・LocalStack Auth Tokenは不要。画面や商品APIはまだ追加していないため、今回はCLIのJSONと自動検証で確認する。

## 1. API用の依存を導入する

```sh
UV_CACHE_DIR="$PWD/.cache/uv" .tools/uv/bin/uv sync --project apps/api --locked
```

| 指定 | 意味 |
| --- | --- |
| UV_CACHE_DIR="$PWD/.cache/uv" | このコマンドのキャッシュをプロジェクト内に置く。シェル設定ファイルを書き換えない |
| --project apps/api | API用のpyproject.toml / uv.lock / .venvを使う |
| --locked | 固定ロックを更新せずに導入。不整合なら失敗する |

Day 6でAPI実行依存にBoto3 / botocore 1.43.121を追加した。infra/local-awsの仮想環境とは分かれている。

## 2. MiniStackを起動する

```sh
docker compose --env-file /dev/null -f compose.yaml up -d --wait
```

| 指定 | 意味 |
| --- | --- |
| --env-file /dev/null | Composeの暗黙の.env読込を避ける。API CLIの--env-fileとは別の指定 |
| -f compose.yaml | Day 3から使う固定イメージ・loopback公開・名前付きボリュームの構成 |
| up -d --wait | バックグラウンドで起動し、ヘルスチェックが通るまで待つ |

成功後は127.0.0.1:4566で利用できる。AWS実環境にリソースを作成するコマンドではない。

## 3. 保存先を初期化する

```sh
UV_CACHE_DIR="$PWD/.cache/uv" .tools/uv/bin/uv run \
  --project apps/api --locked \
  sales-manager-data --env-file apps/api/.env.example init
```

`uv run`はAPIの仮想環境で後続のCLIを動かす。`sales-manager-data`はDay 6で追加した管理用CLI。`--env-file`は直後の設定見本だけを明示的に読み、既存の`.env`を変更しない。OS環境変数が見本より優先されるため、出力のtable / storeが意図した値か確認する。

| 出力 | 期待値 |
| --- | --- |
| table | sales-manager-local |
| store | demo |
| created | 初回true、同じテーブルへの再実行はfalse |

作成するのはPK/SKが文字列、PAY_PER_REQUEST、追加索引なしのテーブル。既存構成が異なる場合は変更せず終了する。initはデータを消去・投入しない。

## 4. 架空の商品を投入し、読み取る

```sh
UV_CACHE_DIR="$PWD/.cache/uv" .tools/uv/bin/uv run \
  --project apps/api --locked \
  sales-manager-data --env-file apps/api/.env.example seed

UV_CACHE_DIR="$PWD/.cache/uv" .tools/uv/bin/uv run \
  --project apps/api --locked \
  sales-manager-data --env-file apps/api/.env.example inspect
```

seedは商品2件・コード予約2件・投入版マーカー1件をまとめて保存する。初回はseeded=true、初期値を保持したままの再実行はfalse。変更済み・部分的なデータがあれば、上書きせず終了コード1で停止する。

inspectは商品パーティションを読み、`product_count: 2`、COFFEEの550円とTEAの330円、各version=1を返す。商品以外の3項目は件数に含まれない。initとseedをもう一度実行し、商品が増えないことも確認できる。

## 5. 自動テストと実際のMiniStack検証

```sh
UV_CACHE_DIR="$PWD/.cache/uv" .tools/uv/bin/uv run \
  --project apps/api --locked pytest apps/api/tests -q

UV_CACHE_DIR="$PWD/.cache/uv" .tools/uv/bin/uv run \
  --project apps/api --locked python scripts/verify_day06_persistence.py

UV_CACHE_DIR="$PWD/.cache/uv" .tools/uv/bin/uv run \
  --project apps/api --locked ruff check --config apps/api/pyproject.toml apps/api scripts

UV_CACHE_DIR="$PWD/.cache/uv" .tools/uv/bin/uv run \
  --project apps/api --locked ruff format --check --config apps/api/pyproject.toml apps/api scripts
```

| コマンド | 確認内容・期待値 |
| --- | --- |
| pytest | SDK境界・型・ページング・条件付き書込・容量制限・初期化・CLI、およびDay 5のHTTP等。88 passed。Docker不要 |
| verify_day06_persistence.py | 実際のMiniStackで10項目を確認。check_count=10、temporary_table_deleted=true。Docker必要 |
| ruff check | 静的検証。All checks passed! |
| ruff format --check | 書式検証。変更は行わない |

実機用スクリプトは毎回一意名の`sales-manager-test-day06-*`テーブルを作成する。既存名を指定した場合は変更せず停止。成功・失敗時とも自身で作成したテーブルを削除する。defaultのsales-manager-localには触れない。`--keep-table`は再起動試験用の上級指定で、成功時だけ検証テーブルを残す。

## 6. 再起動・再作成後の保持を確かめる

手順4の初期データがある状態で実行する。

```sh
docker compose --env-file /dev/null -f compose.yaml restart aws-local
docker compose --env-file /dev/null -f compose.yaml up -d --wait

UV_CACHE_DIR="$PWD/.cache/uv" .tools/uv/bin/uv run \
  --project apps/api --locked \
  sales-manager-data --env-file apps/api/.env.example inspect

docker compose --env-file /dev/null -f compose.yaml down
docker compose --env-file /dev/null -f compose.yaml up -d --wait

UV_CACHE_DIR="$PWD/.cache/uv" .tools/uv/bin/uv run \
  --project apps/api --locked \
  sales-manager-data --env-file apps/api/.env.example inspect
```

restartはコンテナの再起動、down / upはコンテナ・ネットワークの削除と再作成。名前付きボリュームを残すため、どちらも商品2件・550円/330円が維持される。`--wait`で準備完了を待ってから読む。ボリュームの削除を意味する`down -v`は今回使わない。

## 7. 必要な場合だけ対象テーブルをリセットする

次の操作は**sales-manager-localテーブル内の全店舗・全データを削除し、空のテーブルを再作成する**。対象が違う場合はDYNAMODB_TABLEと確認名をそろえる。作業データを残す場合はこの節を実行しない。

```sh
UV_CACHE_DIR="$PWD/.cache/uv" .tools/uv/bin/uv run \
  --project apps/api --locked \
  sales-manager-data --env-file apps/api/.env.example \
  reset --confirm-table sales-manager-local

UV_CACHE_DIR="$PWD/.cache/uv" .tools/uv/bin/uv run \
  --project apps/api --locked \
  sales-manager-data --env-file apps/api/.env.example inspect
```

`--confirm-table`は削除対象の正確な名前を要求する。確認名が不一致ならSDK生成前に終了コード2で拒否する。成功後のinspectはproduct_count=0。商品を戻したい場合は手順4のseedを明示的に実行する。他テーブル・S3・Cognito・ボリュームは削除しない。

## 8. 終了する

```sh
docker compose --env-file /dev/null -f compose.yaml down
```

コンテナは停止・削除され、名前付きボリュームと.venv / .cacheは残る。API・Next.jsのサーバーはこの手順では起動しない。[保存層の仕様](PERSISTENCE.md)、[検証結果](DAY6_REVIEW.md)も参照する。
