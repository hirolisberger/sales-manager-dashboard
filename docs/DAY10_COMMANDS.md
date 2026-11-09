# Day 10：売上の訂正・取消・履歴を確認するコマンド

すべてプロジェクトルートsales-manager-dashboard/で実行する。Python 3.14.9・uv 0.13.6・固定MiniStackを使う。API用.venvはuvが選ぶためactivateは不要。以下は架空商品1件・売上1件を追加する。既存の売上IDを流用しない。

## 1. 依存・MiniStack・テーブル

```sh
UV_CACHE_DIR="$PWD/.cache/uv" .tools/uv/bin/uv sync --project apps/api --locked
docker compose --env-file /dev/null -f compose.yaml up -d --wait
UV_CACHE_DIR="$PWD/.cache/uv" .tools/uv/bin/uv run \
  --project apps/api --locked \
  sales-manager-data --env-file apps/api/.env.example init
```

UV_CACHE_DIRはプロジェクト内のキャッシュ。--projectはAPI環境、--lockedはロック不変での導入。Composeの--env-file /dev/nullは暗黙の.env読込を避け、-fで固定設定、up -d --waitはバックグラウンド起動と準備待ち。initは既存データを消さず、未作成のテーブルを作る。見本はlocal・table=sales-manager-local・store=demo。OS環境変数が優先されるので独自設定時は接続先を確認する。

## 2. ターミナルAでAPIを起動

```sh
UV_CACHE_DIR="$PWD/.cache/uv" .tools/uv/bin/uv run \
  --project apps/api --locked \
  sales-manager-api --env-file apps/api/.env.example
```

127.0.0.1:8000で待つ。以前のAPIが動いている場合はそのターミナルでCtrl+Cし、今のコードで起動する。--port 8001などを付ける場合は以下のURLも変更する。以降は同じルートのターミナルBで順番に実行する。シェル変数を後の手順で使うため同じターミナルを使う。

## 3. 確認用の商品を作る

```sh
mkdir -p .cache
python3 - <<'PY'
import json
from pathlib import Path
from uuid import uuid4
Path('.cache/day10-product-key.txt').write_text(str(uuid4()))
Path('.cache/day10-product-body.json').write_text(json.dumps({
    'code': 'REVIEW10-' + uuid4().hex[:8].upper(),
    'name': 'レビュー用コーヒー', 'default_unit_price_yen': 550,
}, ensure_ascii=False))
PY
curl -sS -o .cache/day10-product.json -w '%{http_code}\n' \
  -X POST http://127.0.0.1:8000/products \
  -H 'Content-Type: application/json' \
  -H "Idempotency-Key: $(cat .cache/day10-product-key.txt)" \
  --data-binary @.cache/day10-product-body.json
```

201が期待値。毎回新しい商品コードと要求UUIDを作る。python3は標準ライブラリのJSON/UUID用途。mkdir -pは既存なら何もしない。.cacheはGit除外される。

| curl指定 | 意味 |
| --- | --- |
| -sS | 進捗を抑え、通信エラーは表示 |
| -o / -D | 応答本文 / 応答ヘッダーを保存 |
| -w '%{http_code}\n' | HTTPステータスを表示 |
| -X / -H | HTTPメソッド / ヘッダー |
| --data-binary @ファイル | 保存したJSONをそのまま送信 |
| -f | HTTPエラー時にcurlも失敗扱い |

## 4. 昨日の売上を登録

```sh
UV_CACHE_DIR="$PWD/.cache/uv" .tools/uv/bin/uv run \
  --project apps/api --locked python - <<'PY'
import json
from datetime import datetime, timedelta
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo
product = json.loads(Path('.cache/day10-product.json').read_text())
day = datetime.now(ZoneInfo('Asia/Tokyo')).date() - timedelta(days=1)
Path('.cache/day10-create-key.txt').write_text(str(uuid4()))
Path('.cache/day10-create-body.json').write_text(json.dumps({
    'sale_date': str(day), 'lines': [{
        'product_id': product['id'], 'unit_price_yen': 550, 'quantity': 2,
    }],
}))
PY
curl -sS -D .cache/day10-created-headers.txt \
  -o .cache/day10-created.json -w '%{http_code}\n' \
  -X POST http://127.0.0.1:8000/sales \
  -H 'Content-Type: application/json' \
  -H "Idempotency-Key: $(cat .cache/day10-create-key.txt)" \
  --data-binary @.cache/day10-create-body.json
day10_sale_id=$(python3 -c 'import json; print(json.load(open(".cache/day10-created.json"))["id"])')
curl -i "http://127.0.0.1:8000/sales/$day10_sale_id"
```

登録201、GET200、ETag: "v1"、quantity=2・合計1,100円。zoneinfoでJST昨日を求める。$day10_sale_idは今回の応答から取得するので、仮のIDを手で置換する必要はない。-iはヘッダーと本文を表示する。

## 5. 数量1へ訂正し、計上日をさらに1日前へ移す

```sh
python3 - <<'PY'
import json
from datetime import date, timedelta
from pathlib import Path
from uuid import uuid4
sale = json.loads(Path('.cache/day10-created.json').read_text())
line = sale['lines'][0]
Path('.cache/day10-patch-key.txt').write_text(str(uuid4()))
Path('.cache/day10-patch-body.json').write_text(json.dumps({
    'sale_date': str(date.fromisoformat(sale['sale_date']) - timedelta(days=1)),
    'lines': [{k: line[k] for k in ['line_id', 'product_id', 'unit_price_yen']} | {'quantity': 1}],
    'reason': '数量と計上日の入力誤りを訂正',
}, ensure_ascii=False))
PY
curl -sS -D .cache/day10-corrected-headers.txt \
  -o .cache/day10-corrected.json -w '%{http_code}\n' \
  -X PATCH "http://127.0.0.1:8000/sales/$day10_sale_id" \
  -H 'Content-Type: application/json' \
  -H 'If-Match: "v1"' \
  -H "Idempotency-Key: $(cat .cache/day10-patch-key.txt)" \
  --data-binary @.cache/day10-patch-body.json
python3 -m json.tool .cache/day10-corrected.json
```

200・version=2・confirmed・合計550円・同じline_idが期待値。If-Matchは手順4で得たETagを送る。この例は確実に新規登録した直後のため"v1"だが、任意の既存売上では必ずGETで最新値を取り直す。{...} | {...}は辞書にquantityを追加するPythonの構文。PATCHは訂正後の全明細と理由を送る。line_idを省略すると新しい明細になる。

元の日付別コピーの削除と新日付への保存も同じトランザクション。旧履歴は変えない。画面は後続Dayで作る。

## 6. 訂正後の売上を取り消す

```sh
python3 - <<'PY'
import json
from pathlib import Path
from uuid import uuid4
Path('.cache/day10-cancel-key.txt').write_text(str(uuid4()))
Path('.cache/day10-cancel-body.json').write_text(json.dumps({'reason': '二重入力のため取消'}, ensure_ascii=False))
PY
curl -sS -D .cache/day10-cancelled-headers.txt \
  -o .cache/day10-cancelled.json -w '%{http_code}\n' \
  -X POST "http://127.0.0.1:8000/sales/$day10_sale_id/cancel" \
  -H 'Content-Type: application/json' \
  -H 'If-Match: "v2"' \
  -H "Idempotency-Key: $(cat .cache/day10-cancel-key.txt)" \
  --data-binary @.cache/day10-cancel-body.json
python3 -m json.tool .cache/day10-cancelled.json
```

200・version=3・cancelled・金額550円と明細を保持。マイナス金額の売上や物理削除にはしない。status=confirmedで検索すると除外され、all/cancelledなら参照できる。取消済みの復活は実装していない。

## 7. 履歴を1件ずつ読む

```sh
curl -fsS --get "http://127.0.0.1:8000/sales/$day10_sale_id/revisions" \
  --data-urlencode 'limit=1' -o .cache/day10-history.json
python3 -m json.tool .cache/day10-history.json
while true; do
  day10_cursor=$(python3 -c 'import json; print(json.load(open(".cache/day10-history.json"))["next_cursor"] or "")')
  if [ -z "$day10_cursor" ]; then
    echo '履歴の終端です。'
    break
  fi
  curl -fsS --get "http://127.0.0.1:8000/sales/$day10_sale_id/revisions" \
    --data-urlencode 'limit=1' --data-urlencode "cursor=$day10_cursor" \
    -o .cache/day10-history.json || break
  python3 -m json.tool .cache/day10-history.json
done
```

版1 created → 版2 corrected → 版3 cancelled、最後はnext_cursor=null。最終項目の次にitems=[]の終端ページを返す場合もある。件数で終了せずnext_cursorで判定する。before/after・reason・actor_id・occurred_atを確認する。--getは検索条件をURLへ付け、--data-urlencodeはカーソルを安全にURLへ変換する。カーソルは直前の応答から取得する。limitを変えず15分以内に使う。期限切れ・API再起動後は最初から取得する。

ブラウザーでもhttp://127.0.0.1:8000/sales/今回の売上ID/revisionsを開くと全履歴のJSONを読める。実際のIDは手順4の応答にある。

## 8. 訂正要求を同じ条件で再送する

```sh
curl -sS -D .cache/day10-replayed-headers.txt \
  -o .cache/day10-replayed.json -w '%{http_code}\n' \
  -X PATCH "http://127.0.0.1:8000/sales/$day10_sale_id" \
  -H 'Content-Type: application/json' \
  -H 'If-Match: "v1"' \
  -H "Idempotency-Key: $(cat .cache/day10-patch-key.txt)" \
  --data-binary @.cache/day10-patch-body.json
cat .cache/day10-replayed-headers.txt
curl -i "http://127.0.0.1:8000/sales/$day10_sale_id"
```

再送は200・Idempotency-Replayed: true・ETag: "v2"で、手順5の初回応答を返す。GETは最新版のcancelled/v3。再送の返答を現在版だと解釈しない。履歴は3件のまま。本文だけを変えて同じ要求キーを使うと409になる。

## 9. 古い版と取消後の変更を拒否する

```sh
day10_new_key=$(python3 -c 'from uuid import uuid4; print(uuid4())')
curl -i -X PATCH "http://127.0.0.1:8000/sales/$day10_sale_id" \
  -H 'Content-Type: application/json' -H 'If-Match: "v1"' \
  -H "Idempotency-Key: $day10_new_key" \
  --data-binary @.cache/day10-patch-body.json
day10_new_key=$(python3 -c 'from uuid import uuid4; print(uuid4())')
curl -i -X PATCH "http://127.0.0.1:8000/sales/$day10_sale_id" \
  -H 'Content-Type: application/json' -H 'If-Match: "v3"' \
  -H "Idempotency-Key: $day10_new_key" \
  --data-binary @.cache/day10-patch-body.json
```

別の新しい要求キーで古い版を送ると412 VERSION_CONFLICT。現在版v3を送っても取消済みなので409 SALE_CANCELLED。失敗時は保存しない。503なら同じ要求をRetry-Afterに従って再送し、412ならGETで最新版を確認する。ローカル管理者用に認証を省略しているためAWS配備用として使わない。

## 10. 自動テスト・静的検証

```sh
UV_CACHE_DIR="$PWD/.cache/uv" .tools/uv/bin/uv run \
  --project apps/api --locked pytest apps/api/tests -q
UV_CACHE_DIR="$PWD/.cache/uv" .tools/uv/bin/uv run \
  --project apps/api --locked python scripts/verify_day10_sale_changes.py
UV_CACHE_DIR="$PWD/.cache/uv" .tools/uv/bin/uv run \
  --project apps/api --locked ruff check --config apps/api/pyproject.toml apps/api scripts
UV_CACHE_DIR="$PWD/.cache/uv" .tools/uv/bin/uv run \
  --project apps/api --locked ruff format --check --config apps/api/pyproject.toml apps/api scripts
```

pytestは330件（追加78件）。訂正・取消・再送・入力・版・商品スナップショット・履歴・カーソル・SDK境界をテストダブルで確認する。実機用スクリプトは実MiniStackの一意名sales-manager-test-day10-*だけを作成・削除し、HTTPはTestClientを使う。既存データには触れない。Ruffは静的/書式検証。[検証記録](DAY10_REVIEW.md)に項目と未検証範囲を記載する。

## 11. 終了

ターミナルAでCtrl+C。手動確認の商品・売上・履歴は残る。今回だけMiniStackを起動した場合、他の利用がないことを確認して停止する。

```sh
docker compose --env-file /dev/null -f compose.yaml down
```

名前付きボリュームを保持する。-v / --volumesやDocker Desktopでのボリューム削除はデータも消すため通常終了には使わない。今回の売上だけを物理削除するAPIはない。
