# Day 8：売上登録を確認するコマンド

すべてプロジェクトルート`sales-manager-dashboard/`で実行する。親の`qiita/`ではないことを`pwd`で確認する。Python 3.14.9・uv 0.13.6・固定版MiniStackを使い、依存の追加・更新はない。uvがAPI用の.venvを使うため、手動activateは不要。以下はローカルテーブルへ確認用の商品と売上を保存する。

## 1. 依存・MiniStack・テーブルを準備する

```sh
UV_CACHE_DIR="$PWD/.cache/uv" .tools/uv/bin/uv sync --project apps/api --locked
docker compose --env-file /dev/null -f compose.yaml up -d --wait
UV_CACHE_DIR="$PWD/.cache/uv" .tools/uv/bin/uv run \
  --project apps/api --locked \
  sales-manager-data --env-file apps/api/.env.example init
```

| 指定 | 意味 |
| --- | --- |
| UV_CACHE_DIR=... | このコマンドのキャッシュをプロジェクト内へ保存 |
| --project apps/api --locked | APIの固定ロックと仮想環境を使用 |
| Composeの--env-file /dev/null | 暗黙の.env読込を避ける |
| -f compose.yaml / up -d --wait | 固定構成でバックグラウンド起動し、準備完了を待つ |
| CLIの--env-file apps/api/.env.example | ローカル用の設定見本を明示読込 |
| init | 未作成のテーブルだけ作成。既存データは消さない |

OS環境変数が見本より優先。出力はtable=sales-manager-local・store=demoが目印。seedは不要。ボリューム削除後でもイメージ・空ボリューム・テーブルをこの手順で再作成できるが、削除前の手動データは戻らない。

## 2. ターミナルAでAPIを起動する

```sh
UV_CACHE_DIR="$PWD/.cache/uv" .tools/uv/bin/uv run \
  --project apps/api --locked \
  sales-manager-api --env-file apps/api/.env.example
```

127.0.0.1:8000で待機する。別のポートなら`--port 8001`を追加し、以下のURLも変更する。APIを動かしたままターミナルBを開き、同じプロジェクトルートへ移動する。

## 3. ターミナルBで有効な確認用商品を登録する

```sh
mkdir -p .cache
python3 - <<'PY'
import json
from pathlib import Path
from uuid import uuid4
Path('.cache/day08-product-key.txt').write_text(str(uuid4()))
Path('.cache/day08-product-body.json').write_text(json.dumps({
    'code': 'REVIEW08-' + uuid4().hex[:8].upper(),
    'name': 'レビュー用コーヒー',
    'default_unit_price_yen': 600,
}, ensure_ascii=False))
PY
curl -sS -D .cache/day08-product-headers.txt \
  -o .cache/day08-product.json -w '%{http_code}\n' \
  -X POST http://127.0.0.1:8000/products \
  -H 'Content-Type: application/json' \
  -H "Idempotency-Key: $(cat .cache/day08-product-key.txt)" \
  --data-binary @.cache/day08-product-body.json
cat .cache/day08-product.json
```

期待値201。有効商品・標準単価600円。UUIDと商品コードを毎回生成するためseed商品を変更しない。python3は標準ライブラリのJSON/UUID作成だけに使う。端末全体の環境変数は変更しない。

| curl指定 | 意味 |
| --- | --- |
| -sS | 進捗を抑え、通信エラーは表示 |
| -D / -o | 応答ヘッダー / 本文をファイルへ保存 |
| -w '%{http_code}\n' | HTTPステータスを表示 |
| -X POST / -H | 登録操作 / JSON形式と要求UUIDを指定 |
| --data-binary @ファイル | 保存したJSONをそのまま送る |

## 4. 売上本文を用意し、登録する

```sh
UV_CACHE_DIR="$PWD/.cache/uv" .tools/uv/bin/uv run \
  --project apps/api --locked python - <<'PY'
import json
from datetime import datetime
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo
product = json.loads(Path('.cache/day08-product.json').read_text())
Path('.cache/day08-sale-key.txt').write_text(str(uuid4()))
Path('.cache/day08-sale-body.json').write_text(json.dumps({
    'sale_date': datetime.now(ZoneInfo('Asia/Tokyo')).date().isoformat(),
    'lines': [{'product_id': product['id'], 'unit_price_yen': 550, 'quantity': 2}],
}, ensure_ascii=False))
PY
curl -sS -D .cache/day08-created-headers.txt \
  -o .cache/day08-created.json -w '%{http_code}\n' \
  -X POST http://127.0.0.1:8000/sales \
  -H 'Content-Type: application/json' \
  -H "Idempotency-Key: $(cat .cache/day08-sale-key.txt)" \
  --data-binary @.cache/day08-sale-body.json
cat .cache/day08-created-headers.txt
python3 -m json.tool .cache/day08-created.json
```

日本時間の実行日を計上日にし、マスタ600円に対して実売550円×2を指定する。期待値201・ETag: "v1"・Idempotency-Replayed: false・total_amount_yen=1100・confirmed・version=1・JPY。明細のline_amount_yenも1100。ID・商品名・作成日時などはサーバーが確定する。json.toolは保存した本文を整形表示するだけ。

## 5. 同じ要求を再送する

**手順4のPythonを再実行せず**に、次のcurlだけを実行する。

```sh
curl -sS -D .cache/day08-replayed-headers.txt \
  -o .cache/day08-replayed.json -w '%{http_code}\n' \
  -X POST http://127.0.0.1:8000/sales \
  -H 'Content-Type: application/json' \
  -H "Idempotency-Key: $(cat .cache/day08-sale-key.txt)" \
  --data-binary @.cache/day08-sale-body.json
cat .cache/day08-replayed-headers.txt
python3 - <<'PY'
import json
from pathlib import Path
first = json.loads(Path('.cache/day08-created.json').read_text())
replayed = json.loads(Path('.cache/day08-replayed.json').read_text())
print('same_response:', first == replayed)
PY
```

期待値201・Idempotency-Replayed: true・same_response: True。売上ID・明細ID・日時・金額も同じで、売上は増えない。別の売上には新しい要求キーを使う。同じキーで本文を変更すると409。まだ処理中の競合で503となった場合は、Retry-Afterを待ち、同じキー・同じ本文で再試行する。

## 6. 保存された本体・日付別データ・履歴を読む

```sh
UV_CACHE_DIR="$PWD/.cache/uv" .tools/uv/bin/uv run \
  --project apps/api --locked python - <<'PY'
import json
from pathlib import Path
from sales_manager_api.aws import dynamodb_client
from sales_manager_api.repository import DynamoRepository
from sales_manager_api.settings import load_settings
settings = load_settings(Path('apps/api/.env.example'))
if settings.app_env not in {'local', 'test'}:
    raise SystemExit('local/test専用です。')
sale = json.loads(Path('.cache/day08-created.json').read_text())
sdk = dynamodb_client(settings)
try:
    repo = DynamoRepository(sdk, settings.dynamodb_table, settings.store_id)
    current = repo.get(repo.key('SALE#' + sale['id'], 'CURRENT'))
    daily = repo.get(repo.key('DAY#' + sale['sale_date'], 'SALE#' + sale['id']))
    revision = repo.get(repo.key('SALE#' + sale['id'], 'REV#0000000001'))
    public = lambda item: {k: v for k, v in item.items() if k not in {'PK', 'SK'}}
    print(json.dumps({
        'sale_id': sale['id'], 'total_amount_yen': current['total_amount_yen'],
        'current_matches_response': public(current) == sale,
        'daily_matches_current': public(daily) == public(current),
        'revision_matches_current': revision['after'] == public(current),
        'operation': revision['operation'],
    }, ensure_ascii=False, indent=2))
finally:
    sdk.close()
PY
```

Day 6のローカル専用SDK・店舗内GetItemで3項目を読み取る。書込や削除はしない。期待値は1100、3つの一致判定true、operation=created。このDayでは売上一覧・詳細GETをまだ実装していないため、ブラウザーで売上を確認する画面やGET APIは後続Dayで追加する。

## 7. 自動テストと静的検証を実行する

```sh
UV_CACHE_DIR="$PWD/.cache/uv" .tools/uv/bin/uv run \
  --project apps/api --locked pytest apps/api/tests -q
UV_CACHE_DIR="$PWD/.cache/uv" .tools/uv/bin/uv run \
  --project apps/api --locked python scripts/verify_day08_sales.py
UV_CACHE_DIR="$PWD/.cache/uv" .tools/uv/bin/uv run \
  --project apps/api --locked ruff check --config apps/api/pyproject.toml apps/api scripts
UV_CACHE_DIR="$PWD/.cache/uv" .tools/uv/bin/uv run \
  --project apps/api --locked ruff format --check --config apps/api/pyproject.toml apps/api scripts
```

pytestは197件。Day 8追加56件は売上HTTP・整数/日付/金額/件数の境界・スナップショット・原子的書込・要求キー・商品競合・店舗/操作者境界をテストダブルで確認する。実機用スクリプトは10項目・temporary_table_deleted=trueが目印。HTTPはTestClient、DBは実MiniStackで、毎回新規のsales-manager-test-day08-*だけを作成・削除する。既存データは変更しない。Ruffは静的/書式検証で、--checkはファイルを変更しない。

## 8. 終了する

ターミナルAでCtrl+C。手動登録した商品と売上は残る。確認のためにMiniStackを起動した場合は、他の利用がないことを確認して停止する。

```sh
docker compose --env-file /dev/null -f compose.yaml down
```

通常のdownは名前付きボリュームを保持する。**-v / --volumesやDocker DesktopのVolumes削除は、保存データも消す操作**。通常の終了に使わない。確認用売上の取消はDay 10、テーブル全体のリセットは [Day 6の明示的な手順](DAY6_COMMANDS.md)で別途行う。
