# Day 5：APIの起動と動作確認コマンド

プロジェクトルート`sales-manager-dashboard/`で実行する。Day 2のPython 3.14.9とuv 0.13.6を使う。Day 5のAPI確認にDockerやMiniStackの起動は不要。

uvの環境変数・`$PWD`・仮想環境の基本は [DAY4_COMMANDS.md](DAY4_COMMANDS.md) を参照する。今回のPython環境は`apps/api/.venv/`で、Day 4の`infra/local-aws/.venv/`とは別になる。

## 1. 依存を導入する

```sh
UV_CACHE_DIR="$PWD/.cache/uv" .tools/uv/bin/uv sync --project apps/api --locked
```

| 指定 | 意味 |
| --- | --- |
| `UV_CACHE_DIR=...` | このuvコマンドのキャッシュをプロジェクト内に置く |
| `--project apps/api` | API用の依存・ロック・仮想環境を選ぶ |
| `--locked` | 固定したロックに合わせ、不整合があれば自動更新せず失敗する |

FastAPIなどの実行用依存と、既定のdevグループにあるpytestなどを導入する。手動のvenv作成・activateは不要。

## 2. ターミナルAでサーバーを起動する

```sh
UV_CACHE_DIR="$PWD/.cache/uv" .tools/uv/bin/uv run \
  --project apps/api --locked \
  sales-manager-api --env-file apps/api/.env.example
```

| 指定 | 意味 |
| --- | --- |
| `uv run` | API用のPython環境で後続コマンドを実行する |
| `sales-manager-api` | APIパッケージに登録したCLIを起動する |
| `--env-file apps/api/.env.example` | CLIがこのダミー設定ファイルを明示的に読む。OS環境変数が優先される |

ここでの`--env-file`は`sales-manager-api`への引数で、Docker Composeへの指定ではない。見本を直接読むため、既存の`.env`を作成・上書きしない。自分の設定ファイルを読む場合は、そのパスに置き換える。省略時はOS環境変数と既定値を使い、dotenvを自動読込しない。

Uvicornが`http://127.0.0.1:8000`で待ち受ける。コマンドは終了せず、起動したまま次のターミナルを使う。Day 2の同名コマンドがメッセージ表示後に終了した動作から変更している。

8000番が使用中なら末尾に`--port 8001`を付け、次のURLも8001へ変更する。CLIは外部向けのhost指定を受け付けず、127.0.0.1に固定している。

## 3. ターミナルBでHTTP応答を確認する

```sh
curl -i http://127.0.0.1:8000/health
```

`-i`は本文と一緒にHTTPヘッダーを表示する指定。200、`content-type: application/json`、`x-request-id`のUUID、本文`{"status":"ok"}`が目印になる。要求IDは毎回変わる。ブラウザーで同じURLを開いて本文を確認することもできる。[curl公式資料](https://curl.se/docs/manpage.html)

続けて共通エラーを確認する。

```sh
curl -i http://127.0.0.1:8000/missing
curl -i -X POST http://127.0.0.1:8000/health
```

| 確認 | 期待値 |
| --- | --- |
| GET /missing | 404、error.codeがNOT_FOUND |
| POST /health | 405、error.codeがMETHOD_NOT_ALLOWED、AllowにGET |
| 両方のエラー | error.request_idとx-request-idヘッダーが一致 |

`-X POST`はHTTPメソッドをPOSTへ変える。curlはこれらの404/405でも通常は終了コード0になるため、HTTPステータスと本文で判定する。400/422/500は、次の自動テストで試験用ルートを使って確認する。例外を発生させるための公開ルートは作らない。

## 4. 自動テストと静的検証を実行する

```sh
UV_CACHE_DIR="$PWD/.cache/uv" .tools/uv/bin/uv run \
  --project apps/api --locked pytest apps/api/tests -q

UV_CACHE_DIR="$PWD/.cache/uv" .tools/uv/bin/uv run \
  --project apps/api --locked ruff check --config apps/api/pyproject.toml apps/api scripts

UV_CACHE_DIR="$PWD/.cache/uv" .tools/uv/bin/uv run \
  --project apps/api --locked ruff format --check --config apps/api/pyproject.toml apps/api scripts
```

pytestは設定・HTTP応答・CLIを確認する。`-q`は表示を簡潔にし、成功の目印は`39 passed`。Ruffのcheckは静的検証、format --checkは書式の検査で、ファイルを自動修正しない。テスト実行時にHTTPサーバーを別途起動しておく必要はない。

Day 4の設計用契約も確認する場合は、専用環境で実行する。

```sh
UV_CACHE_DIR="$PWD/.cache/uv" .tools/uv/bin/uv run \
  --project infra/local-aws --group contracts --locked \
  python scripts/verify_day04_contract.py
```

期待値は6テストグループ成功。共通500と要求IDヘッダーを追加したYAML全体を確認する。

## 5. サーバーを停止する

ターミナルAで`Ctrl+C`を押す。Uvicornが終了し、8000番の待受が閉じる。今回の手順ではコンテナやAWSリソースを作成しないため、DockerのdownやAWSの削除操作は発生しない。

`.venv/`・`.cache/uv/`・pytest/Ruffのキャッシュは残る。アプリは個人のAWS設定を読む処理やSDK通信をまだ持たない。設定が不正なら起動時に停止するため、接続拒否の場合はターミナルAの起動結果も確認する。

仕様は [API_FOUNDATION.md](API_FOUNDATION.md)、検証実績は [DAY5_REVIEW.md](DAY5_REVIEW.md) に記録する。
