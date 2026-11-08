# Day 9：売上検索・詳細・ページングの確認コマンド

すべてプロジェクトルート`sales-manager-dashboard/`で実行する。`pwd`で親のqiita/ではないことを確認。Python 3.14.9・uv 0.13.6・固定MiniStackを使い、依存の追加・更新はない。uvがAPI用.venvを使うため手動activateは不要。以下はローカルに確認用の商品2件・売上4件を追加する。

## 1. 依存・MiniStack・テーブルを準備する

```sh
UV_CACHE_DIR="$PWD/.cache/uv" .tools/uv/bin/uv sync --project apps/api --locked
docker compose --env-file /dev/null -f compose.yaml up -d --wait
UV_CACHE_DIR="$PWD/.cache/uv" .tools/uv/bin/uv run \
  --project apps/api --locked \
  sales-manager-data --env-file apps/api/.env.example init
```

UV_CACHE_DIRはプロジェクト内キャッシュ、--projectはAPI環境、--lockedはロック不変での導入。Composeの--env-file /dev/nullは暗黙の.env読込を避け、-fで固定構成、up -d --waitでバックグラウンド起動・準備完了を待つ。initは未作成テーブルだけを作り、既存データは消さない。

設定見本のtable=sales-manager-local・store=demoが目印。OS環境変数が見本より優先される。seedは不要。

## 2. ターミナルAでAPIを起動する

```sh
UV_CACHE_DIR="$PWD/.cache/uv" .tools/uv/bin/uv run \
  --project apps/api --locked \
  sales-manager-api --env-file apps/api/.env.example
```

127.0.0.1:8000で待ち受ける。既に別APIが起動中ならそのターミナルでCtrl+Cし、現在のコードで起動し直す。別ポートを使う場合は--port 8001を追加し、以下のURLも変更する。ターミナルBも同じプロジェクトルートへ移動する。

## 3. ターミナルBで確認用商品を登録する

```sh
mkdir -p .cache
python3 - <<'PY'
import json
from pathlib import Path
from uuid import uuid4
for kind, name, price in [('coffee', 'レビュー用コーヒー', 550), ('tea', 'レビュー用紅茶', 330)]:
    Path(f'.cache/day09-{kind}-key.txt').write_text(str(uuid4()))
    Path(f'.cache/day09-{kind}-body.json').write_text(json.dumps({
        'code': 'REVIEW09-' + uuid4().hex[:8].upper(),
        'name': name, 'default_unit_price_yen': price,
    }, ensure_ascii=False))
PY
for day09_kind in coffee tea; do
  curl -sS -o ".cache/day09-$day09_kind.json" -w '%{http_code}\n' \
    -X POST http://127.0.0.1:8000/products \
    -H 'Content-Type: application/json' \
    -H "Idempotency-Key: $(cat ".cache/day09-$day09_kind-key.txt")" \
    --data-binary "@.cache/day09-$day09_kind-body.json"
done
```

期待値201が2回。毎回新しいコードとUUIDを作るため既存商品を変更しない。python3は標準ライブラリのJSON/UUID用途。forの変数はこのターミナル内だけで、シェル設定は変更しない。

| curl指定 | 意味 |
| --- | --- |
| -sS / -o | 進捗を抑え通信エラーを表示 / 応答本文をファイル保存 |
| -w '%{http_code}\n' | HTTPステータスを表示 |
| -X POST / -H | 登録メソッド / JSON形式と要求キー |
| --data-binary @ファイル | ファイルのJSONをそのまま送る |

## 4. 過去日・当日の売上を4件登録する

```sh
UV_CACHE_DIR="$PWD/.cache/uv" .tools/uv/bin/uv run \
  --project apps/api --locked python - <<'PY'
import json
from datetime import datetime, timedelta
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo
coffee = json.loads(Path('.cache/day09-coffee.json').read_text())['id']
tea = json.loads(Path('.cache/day09-tea.json').read_text())['id']
today = datetime.now(ZoneInfo('Asia/Tokyo')).date()
def line(product, price, quantity):
    return {'product_id': product, 'unit_price_yen': price, 'quantity': quantity}
cases = [
    (today - timedelta(days=2), [line(coffee, 550, 2), line(tea, 330, 1)]),
    (today - timedelta(days=1), [line(tea, 330, 2)]),
    (today, [line(coffee, 550, 1)]),
    (today, [line(tea, 330, 1)]),
]
for number, (day, lines) in enumerate(cases, 1):
    Path(f'.cache/day09-sale{number}-key.txt').write_text(str(uuid4()))
    Path(f'.cache/day09-sale{number}-body.json').write_text(json.dumps({'sale_date': str(day), 'lines': lines}))
Path('.cache/day09-query.json').write_text(json.dumps({
    'start_date': str(today - timedelta(days=2)), 'end_date': str(today),
    'product_id': tea, 'status': 'all', 'limit': '1',
}))
PY
for day09_number in 1 2 3 4; do
  curl -sS -o ".cache/day09-sale$day09_number.json" -w '%{http_code}\n' \
    -X POST http://127.0.0.1:8000/sales \
    -H 'Content-Type: application/json' \
    -H "Idempotency-Key: $(cat ".cache/day09-sale$day09_number-key.txt")" \
    --data-binary "@.cache/day09-sale$day09_number-body.json"
done
```

期待値201が4回。金額は順に1,430円・660円・550円・330円。日本時間の実行日を基準にする。別の売上ごとに新しい要求UUIDを使う。検索条件ファイルは紅茶だけ・3日間・1件ずつで、既存データが同じ期間にあっても今回の紅茶IDだけを対象にできる。

## 5. 売上詳細とETagを確認する

```sh
day09_sale_id=$(python3 -c 'import json; print(json.load(open(".cache/day09-sale1.json"))["id"])')
curl -i "http://127.0.0.1:8000/sales/$day09_sale_id"
```

200・ETag: "v1"・2明細・合計1,430円。詳細は紅茶で絞らず全明細を返す。-iは応答ヘッダーも表示する。

## 6. 一覧を取得し、次のページへ進む

```sh
day09_query=$(python3 -c 'import json, urllib.parse; print(urllib.parse.urlencode(json.load(open(".cache/day09-query.json"))))')
curl -fsS "http://127.0.0.1:8000/sales?$day09_query" \
  -o .cache/day09-page.json
python3 -m json.tool .cache/day09-page.json
```

200・itemsに当日の紅茶売上330円が1件。urlencodeで日付・UUIDを検索条件へ変換し、-fはHTTPエラー時にcurlを失敗扱いにする。json.toolは保存したJSONを整形するだけ。

次を繰り返すと**直前の応答から**next_cursorを取り出して進む。仮の文字列をコピーする必要はない。

```sh
day09_next_query=$(python3 - <<'PY'
import json
from urllib.parse import urlencode
params = json.load(open('.cache/day09-query.json'))
cursor = json.load(open('.cache/day09-page.json'))['next_cursor']
print(urlencode({**params, 'cursor': cursor}) if cursor is not None else '')
PY
)
if [ -n "$day09_next_query" ]; then
  curl -fsS "http://127.0.0.1:8000/sales?$day09_next_query" \
    -o .cache/day09-page.json
  python3 -m json.tool .cache/day09-page.json
else
  echo '次のページはありません。'
fi
```

同じコマンドを繰り返し、紅茶に一致する当日330円・前日660円・2日前の売上を新しい順で確認する。2日前の行はtotal_amount_yen=1430、matched_amount_yen=330、matched_quantity=1。itemsが空でもnext_cursorが文字列なら続け、nullが終端。

カーソル取得後に条件を変えた場合、15分経過した場合、APIを再起動した場合は400 INVALID_CURSOR。手順6の最初のコマンドで取り直す。商品・期間・status・limitは途中で変更しない。

ブラウザーで見るURLは次で表示できる。生成されたURLを開くとJSONを読める。売上管理画面は後続Day。

```sh
printf 'http://127.0.0.1:8000/sales?%s\n' "$day09_query"
```

## 7. テストと静的検証

```sh
UV_CACHE_DIR="$PWD/.cache/uv" .tools/uv/bin/uv run \
  --project apps/api --locked pytest apps/api/tests -q
UV_CACHE_DIR="$PWD/.cache/uv" .tools/uv/bin/uv run \
  --project apps/api --locked python scripts/verify_day09_sale_queries.py
UV_CACHE_DIR="$PWD/.cache/uv" .tools/uv/bin/uv run \
  --project apps/api --locked ruff check --config apps/api/pyproject.toml apps/api scripts
UV_CACHE_DIR="$PWD/.cache/uv" .tools/uv/bin/uv run \
  --project apps/api --locked ruff format --check --config apps/api/pyproject.toml apps/api scripts
```

pytestは252件。追加55件で期間・状態・商品・詳細・内部ページ分割・カーソル・店舗境界・読取予算などをテストダブルで確認。実機用スクリプトは10項目・temporary_table_deleted=trueが目印。HTTPはTestClient、DBは実MiniStackで、一意名のsales-manager-test-day09-*だけを作成・削除する。取消状態の試験は専用テーブルの人工データで、取消APIはDay 10に実装する。Ruffは静的/書式検証。

## 8. 終了する

ターミナルAでCtrl+C。確認用の商品と売上は残る。今回の確認のためにMiniStackを起動した場合は、他の利用がないことを確認して停止する。

```sh
docker compose --env-file /dev/null -f compose.yaml down
```

名前付きボリュームは保持する。-v / --volumesやDocker DesktopのVolumes削除はデータも消すため、通常の終了には使わない。[検索仕様](SALE_QUERIES.md)と[検証記録](DAY9_REVIEW.md)も参照する。
