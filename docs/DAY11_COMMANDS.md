# Day 11：画面とPython APIの接続確認コマンド

各ターミナルでプロジェクトルートsales-manager-dashboard/を開く。Node.js 24.22.2 / npm 11.19.1 / uv 0.13.6 / Python 3.14.9とDockerを使う。[導入手順](DEVELOPMENT.md)で実行環境を用意済みであることが前提。今回はブラウザーで画面も確認できる。

## 1. 実行環境と依存

このMacのプロジェクト内ツールを使う場合、各ターミナルで最初に次を実行する。他の環境では導入済みの同じバージョンを使う。

```sh
export PATH="$PWD/.tools/node-v24.22.2-darwin-arm64/bin:$PWD/.tools/uv/bin:$PATH"
export UV_CACHE_DIR="$PWD/.cache/uv"
node --version
npm --version
npm --prefix apps/web ci
.tools/uv/bin/uv sync --project apps/api --locked
```

PATHは今のターミナルだけでプロジェクト内のNode.js/uvを優先する。シェル設定やグローバルのNode/Pythonは変更しない。npm --prefixはwebのpackage-lock.jsonを使い、ciで固定依存を再導入する。uvはAPIの.venvを使うためactivateは不要。キャッシュはプロジェクト内に置く。

## 2. MiniStackと確認専用テーブル

```sh
docker compose --env-file /dev/null -f compose.yaml up -d --wait
DYNAMODB_TABLE=sales-manager-test-day11-review .tools/uv/bin/uv run \
  --project apps/api --locked \
  sales-manager-data --env-file apps/api/.env.example init
```

Composeは暗黙の.env読込を避け、固定設定でバックグラウンド起動・準備待ちする。initは未作成なら作り、既存データを消さない。Day 11確認用テーブルを使い、従来のsales-manager-localを変更しない。OS環境変数が見本より優先されるので、独自設定時は接続先とSTORE_IDも確認する。

## 3. ターミナルA：Python API

```sh
DYNAMODB_TABLE=sales-manager-test-day11-review .tools/uv/bin/uv run \
  --project apps/api --locked \
  sales-manager-api --env-file apps/api/.env.example
```

127.0.0.1:8000で待つ。8000番で以前のAPIが動いている場合は、そのターミナルでCtrl+Cし、今回の専用テーブルで起動し直す。他のAPIを止めたくない場合は--port 8001を付け、以下のAPI_BASE_URLとcurlも8001へ変える。

## 4. ターミナルB：Next.js

手順1のPATH設定をこのターミナルでも行い、次を実行する。

```sh
API_BASE_URL=http://127.0.0.1:8000 npm --prefix apps/web run dev -- --port 3000
```

API_BASE_URLはこのNext.jsプロセスだけに渡す。既存の.env.localは書き換えない。NEXT_PUBLIC_は付けない。npmの--より後はNext.jsへ渡す指定で、3000番が使用中なら--port 3001へ変える。

ブラウザーでhttp://127.0.0.1:3000を開く。ホーム・商品参照・更新ボタンと共通ナビゲーションが表示される。新しい専用テーブルなら「商品はまだ登録されていません」。これは通信成功の空結果。http://127.0.0.1:3000/connectionでは「APIに接続できました」と表示される。こちらは保存先の確認ではない。

## 5. ターミナルC：確認用商品を3件登録

```sh
mkdir -p .cache
python3 - <<'PY'
import json
from pathlib import Path
from uuid import uuid4
for number, (name, price) in enumerate([('コーヒー', 550), ('紅茶', 330), ('ケーキ', 440)], 1):
    Path(f'.cache/day11-product{number}-key.txt').write_text(str(uuid4()))
    Path(f'.cache/day11-product{number}-body.json').write_text(json.dumps({
        'code': 'REVIEW11-' + uuid4().hex[:8].upper(),
        'name': name, 'default_unit_price_yen': price,
    }, ensure_ascii=False))
PY
for day11_number in 1 2 3; do
  curl -sS -o ".cache/day11-product$day11_number.json" -w '%{http_code}\n' \
    -X POST http://127.0.0.1:8000/products \
    -H 'Content-Type: application/json' \
    -H "Idempotency-Key: $(cat ".cache/day11-product$day11_number-key.txt")" \
    --data-binary "@.cache/day11-product$day11_number-body.json"
done
```

201が3回。python3は標準ライブラリでJSONとUUIDを作る。コード・要求キーが毎回異なり、既存商品を上書きしない。curlの-sSは通信エラー表示、-oは応答の保存、-wはHTTPステータス、-X POSTは登録、-HはJSON/要求キーのヘッダー、--data-binary @ファイルは本文送信。

ホームの「最新の状態に更新」を押す。商品名・コード・税込標準単価が表示される。順番は商品UUID順で、登録順や名称順ではない。有効商品の先頭3件だけで、繰り返して4件以上になった場合は「ほかにも有効な商品が登録されています」と案内する。

## 6. APIと画面の確認箇所

```sh
curl -i http://127.0.0.1:8000/health
curl -i 'http://127.0.0.1:8000/products?is_active=true&limit=3'
```

-iはヘッダーも表示する。どちらも200。healthはstatus=ok、productsはitemsとnext_cursorを返す。画面はこのAPIをNext.jsサーバーから読む。

ブラウザーでホームと接続確認を行き来し、選択中のナビゲーション、更新ボタン、幅を狭くした表示を確認する。存在しないURLでは404画面が出る。通常の画面操作から商品や売上は変更しない。

## 7. API停止と復帰

ターミナルAでCtrl+Cし、画面の更新ボタンを押す。「データを取得できませんでした」と表示される。ホームと接続確認をそれぞれ更新して確認する。ターミナルAで手順3を再実行し、もう一度更新すると復帰する。

タイムアウトは5秒。通常のローカル通信では読込中表示が短いため、遅延・空結果・HTTP障害・不正JSONを確実に見る試験は手順9で行う。MiniStackを止める必要はない。

## 8. 自動テスト・静的検証・本番ビルド

```sh
npm --prefix apps/web run test
npm --prefix apps/web run lint
npm --prefix apps/web run typecheck
npm --prefix apps/web run build
.tools/uv/bin/uv run --project apps/api --locked \
  ruff check --config apps/api/pyproject.toml apps/api scripts
node --check scripts/verify_day11_web.mjs
```

testはNode標準の53件で接続先・通信条件・応答型・HTTPエラー・タイムアウトを確認する。追加のテスト依存は不要。lintはBiome、typecheckはNext.jsの型生成とtsc、buildは本番用ファイルの作成。APIが止まっていてもビルド可能。RuffはPythonの静的検証、node --checkはブラウザー試験スクリプトの構文検査。

## 9. 自動の実ブラウザー・実MiniStack確認

手順8の本番ビルドが必要。Chromeの試験はインストール済みのGoogle Chromeを使う。macOS以外などで見つからなければ、DAY11_CHROME_PATHで実行ファイルを指定する。

```sh
node scripts/verify_day11_web.mjs
.tools/uv/bin/uv run --project apps/api --locked python scripts/verify_day11_live.py
```

前者は専用Next.js・架空API・一時Chromeプロファイルで12項目。遅延/5秒タイムアウト・障害復帰・ナビ・390px/1365px・404を確認する。普段のブラウザープロファイルは使わない。画像と結果は.cache/day11-web/に保存し、APIとブラウザーは終了する。Chromeのプロファイルは削除する。

後者は実Python APIとMiniStackで9項目。ランダム名sales-manager-test-day11-*のテーブル・専用ポートだけを使い、商品登録・更新反映・無効商品の除外・保存先障害とhealthの違いを確認する。成功・失敗時とも自身のテーブルとサーバーを片付ける。既存の確認専用テーブルや稼働中のAPI・MiniStackは止めない。

## 10. 本番モードを手元で確認

ターミナルBの開発サーバーをCtrl+Cで終了してから、手順1の環境設定があるターミナルで実行する。

```sh
API_BASE_URL=http://127.0.0.1:8000 npm --prefix apps/web run start -- --port 3000
```

同じブラウザーURLで表示と更新を確認する。startは手順8で作ったビルドを使う。開発時だけの画面と混同しない。

終了はA/BそれぞれCtrl+C。専用確認テーブルと手動登録商品は残る。今回MiniStackを起動した場合だけ、他の利用がないことを確認して通常のdocker compose downを使う。もともと起動していたMiniStackやボリュームは削除しない。[仕様](WEB_FOUNDATION.md)と[確認結果](DAY11_REVIEW.md)も参照。
