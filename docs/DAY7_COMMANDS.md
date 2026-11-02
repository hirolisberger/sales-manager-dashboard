# Day 7：商品APIを確認するコマンド

すべてプロジェクトルート`sales-manager-dashboard/`で実行する。Python 3.14.9、uv 0.13.6、Day 3のMiniStack構成を使用。今回のuvは`.tools/uv/bin/uv`に配置している。別の配置ならその部分を自身のuvへ置き換える。venvの作成・activateはuvが担当し、個人のAWS資格情報は不要。

## 1. 依存・MiniStack・保存先を準備する

```sh
UV_CACHE_DIR="$PWD/.cache/uv" .tools/uv/bin/uv sync --project apps/api --locked
docker compose --env-file /dev/null -f compose.yaml up -d --wait

UV_CACHE_DIR="$PWD/.cache/uv" .tools/uv/bin/uv run \
  --project apps/api --locked \
  sales-manager-data --env-file apps/api/.env.example init
```

| 指定 | 意味 |
| --- | --- |
| UV_CACHE_DIR=... | uvのキャッシュをプロジェクト内に置く。シェル設定を変えない |
| --project apps/api --locked | APIの依存・固定ロック・.venvを使用する |
| Composeの--env-file /dev/null | Composeの暗黙の.env読込を避ける |
| up -d --wait | バックグラウンド起動とヘルスチェック待ち |
| CLIの--env-file apps/api/.env.example | API用のダミー設定を明示的に読み込む。OS環境変数が優先 |
| init | 未作成ならテーブル作成。既存なら構成確認。データは削除・投入しない |

見本はlocalモード、table=sales-manager-local、store=demo。initのcreatedは初回true、既存ならfalse。Day 6のseedは任意で、商品APIの利用自体に初期商品は不要。以下はこのテーブルへ確認用商品を保存する操作になる。

## 2. ターミナルAでAPIを起動する

```sh
UV_CACHE_DIR="$PWD/.cache/uv" .tools/uv/bin/uv run \
  --project apps/api --locked \
  sales-manager-api --env-file apps/api/.env.example
```

127.0.0.1:8000で待ち受ける。既に使用中なら`--port 8001`を追加し、以下の8000もそろえて変更する。APIを起動したままターミナルBを開き、同じプロジェクトルートへ移動する。

## 3. ターミナルBで確認用の商品と要求キーを用意する

```sh
mkdir -p .cache
python3 - <<'PY'
import json
from pathlib import Path
from uuid import uuid4
Path('.cache/day07-create-key.txt').write_text(str(uuid4()))
Path('.cache/day07-create-body.json').write_text(json.dumps({
    'code': 'REVIEW07-' + uuid4().hex[:8].upper(),
    'name': 'レビュー用コーヒー',
    'default_unit_price_yen': 550,
}, ensure_ascii=False))
PY
```

毎回新しい商品コードと要求UUIDを作り、既存のseed商品と衝突させない。確認用ファイルだけをGit除外の.cacheへ保存する。`python3`はJSONとUUIDを作る標準ライブラリ用途。アプリ本体はuvが選ぶPython環境で動作する。

## 4. 商品を登録し、同じ要求を再送する

```sh
curl -sS -D .cache/day07-created-headers.txt \
  -o .cache/day07-created.json -w '%{http_code}\n' \
  -X POST http://127.0.0.1:8000/products \
  -H 'Content-Type: application/json' \
  -H "Idempotency-Key: $(cat .cache/day07-create-key.txt)" \
  --data-binary @.cache/day07-create-body.json

cat .cache/day07-created-headers.txt
cat .cache/day07-created.json
```

| 指定 | 意味 |
| --- | --- |
| -sS | 進捗表示を抑え、通信失敗は表示する |
| -D ファイル | 応答ヘッダーを保存する |
| -o ファイル | JSON本文を保存する |
| -w '%{http_code}\n' | HTTPステータスを表示する |
| -X POST | 商品登録のHTTPメソッド |
| -H | JSON形式と、要求を識別するUUIDをヘッダーで渡す |
| --data-binary @ファイル | ファイル内のJSONを送信する |

期待値は201、ETag: "v1"、Idempotency-Replayed: false。本文はid・コード・名称・550円・is_active=true・version=1・UTC日時。表示したIDは以降の詳細・更新に使用する。

**手順3を実行し直さずに、このcurlをもう一度実行**すると、同じUUID・本文の再送になる。201と同じ商品を返し、Idempotency-Replayed: trueになる。商品は増えない。別の新規操作には新しい要求キーを使う。

## 5. 詳細・一覧を確認する

```sh
day07_product_id=$(python3 -c 'import json; print(json.load(open(".cache/day07-created.json"))["id"])')

curl -i "http://127.0.0.1:8000/products/$day07_product_id"
curl -i 'http://127.0.0.1:8000/products?is_active=true&limit=1'
```

`day07_product_id`はこのターミナルだけの変数で、シェル設定ファイルは変更しない。詳細は200とETag、一覧は200とitems / next_cursorを返す。既存商品がある場合、一覧の最初の商品が今回の商品とは限らない。ブラウザーで`http://127.0.0.1:8000/products`や詳細URLを開いてJSONを読むこともできる。商品管理画面はDay 12の予定。

next_cursorが文字列なら、同じlimit・is_activeを使って次を取得する。値をコピーしてCURSOR_FROM_RESPONSEを置き換える。

```sh
curl -i --get http://127.0.0.1:8000/products \
  --data-urlencode 'limit=1' \
  --data-urlencode 'is_active=true' \
  --data-urlencode 'cursor=CURSOR_FROM_RESPONSE'
```

`--get`は値をURLの検索条件へ付け、`--data-urlencode`は値をURLエンコードする。next_cursor=nullで終端。15分経過・改ざん・条件変更・API再起動後は400 INVALID_CURSORとなり、最初から取得する。この例のプレースホルダーをそのまま送ると400になる。

## 6. 名称と単価を更新する

新規登録した商品のETagは"v1"。今回の流れで最初の更新に使用する。既に更新済みなら詳細を再取得し、そのETagを使う。

```sh
day07_update_key=$(python3 -c 'from uuid import uuid4; print(uuid4())')
curl -i -X PATCH "http://127.0.0.1:8000/products/$day07_product_id" \
  -H 'Content-Type: application/json' \
  -H "Idempotency-Key: $day07_update_key" \
  -H 'If-Match: "v1"' \
  --data '{"name":"レビュー用コーヒー改","default_unit_price_yen":600}'
```

期待値は200・ETag: "v2"・version=2。商品ID・コード・created_atは維持する。If-Matchは、読んだ版から変更されていないことを確認する条件。ヘッダー全体を単一引用符で囲むことで、ETagの二重引用符をそのまま送る。

同じ更新の再送は同じday07_update_key・本文・If-Matchを使う。別の更新には新しいキーと最新ETagを使う。要求キーを再利用して内容やIf-Matchを変えると409になる。

## 7. 無効化し、絞り込みと古い版の拒否を確かめる

```sh
day07_disable_key=$(python3 -c 'from uuid import uuid4; print(uuid4())')
curl -i -X PATCH "http://127.0.0.1:8000/products/$day07_product_id" \
  -H 'Content-Type: application/json' \
  -H "Idempotency-Key: $day07_disable_key" \
  -H 'If-Match: "v2"' \
  --data '{"is_active":false}'

curl -i 'http://127.0.0.1:8000/products?is_active=false'
curl -i "http://127.0.0.1:8000/products/$day07_product_id"
```

無効化は200・ETag: "v3"・is_active=false。無効商品一覧と詳細で参照でき、有効商品一覧からは除外する。商品自体とコード予約を削除しない。

新しい要求キーで古い版を使い、更新が拒否されることを確認する。

```sh
day07_stale_key=$(python3 -c 'from uuid import uuid4; print(uuid4())')
curl -i -X PATCH "http://127.0.0.1:8000/products/$day07_product_id" \
  -H 'Content-Type: application/json' \
  -H "Idempotency-Key: $day07_stale_key" \
  -H 'If-Match: "v1"' \
  --data '{"name":"古い版からの更新"}'
```

期待値は412 VERSION_CONFLICT。保存値とversion=3は変わらない。curlはHTTPの4xxでも通常は終了コード0なので、ステータス・本文を確認する。

## 8. 自動検証を実行する

```sh
UV_CACHE_DIR="$PWD/.cache/uv" .tools/uv/bin/uv run \
  --project apps/api --locked pytest apps/api/tests -q

UV_CACHE_DIR="$PWD/.cache/uv" .tools/uv/bin/uv run \
  --project apps/api --locked python scripts/verify_day07_products.py

UV_CACHE_DIR="$PWD/.cache/uv" .tools/uv/bin/uv run \
  --project apps/api --locked ruff check --config apps/api/pyproject.toml apps/api scripts

UV_CACHE_DIR="$PWD/.cache/uv" .tools/uv/bin/uv run \
  --project apps/api --locked ruff format --check --config apps/api/pyproject.toml apps/api scripts
```

pytestは141件成功が目印。Docker不要で、保存層のテストダブルを使ったHTTPテストと既存基盤を含む。実機用スクリプトはHTTP部分をTestClientで処理し、DBだけ実際のMiniStackへ接続する。12項目成功・temporary_table_deleted=trueが目印。別のサーバー起動は不要で、既存データに触れず一意名の専用テーブルを削除する。Ruffは静的・書式検証で、--checkはファイルを修正しない。

## 9. 終了する

ターミナルAでCtrl+C。確認用の商品と要求記録はDynamoDBに残る。今回は物理削除APIを設けないため、商品は無効状態で保持する。手順3から再確認すると新しいコードの商品を別に作成する。

MiniStackも今回の確認のために起動した場合は、他の利用がないことを確認して通常のdownで停止する。ボリュームは残す。

```sh
docker compose --env-file /dev/null -f compose.yaml down
```

テーブル全消去が必要な場合だけ [Day 6のリセット手順](DAY6_COMMANDS.md) を使う。テーブル内の全店舗データが対象であるため、通常の確認では実行しない。仕様は [PRODUCT_API.md](PRODUCT_API.md)、検証内容は [DAY7_REVIEW.md](DAY7_REVIEW.md) を参照。
