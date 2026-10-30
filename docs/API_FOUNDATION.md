# Day 5：Python APIの土台

2026-10-30作成・レビュー承認済み（対象6f52323）。Day 4の[API仕様書](API_CONTRACT.md)を実装し始める。現在の公開ルートは`GET /health`だけで、商品・売上・認証・CSVは各Dayで追加する。

Day 6の追加：SDKクライアントと保存層・管理CLIを [PERSISTENCE.md](PERSISTENCE.md) に実装した。以下の「Day 5では未実装」はDay 5時点の境界を示す。healthの通信不要・API仕様YAMLの正本は維持する。

## 採用した構成

| 役割 | 固定したバージョン・方針 |
| --- | --- |
| API | FastAPI 0.162.0 |
| ASGI実行 | Uvicorn 0.54.0、CLIは127.0.0.1だけにバインド |
| 基盤 | Starlette 1.10.0 |
| モデル・設定 | Pydantic 2.14.2、pydantic-settings 2.16.2 |
| テスト | pytest 9.2.0、HTTPX2 2.16.0、jsonschema 4.26.0、PyYAML 6.0.3 |

FastAPIをHTTPの振り分けと入力検証に、UvicornをASGIサーバーに使う。アプリ生成を`create_app`へ分け、設定を渡したテストとサーバー起動で同じアプリを使用する。[FastAPI公式](https://fastapi.tiangolo.com/tutorial/first-steps/)

バージョンと依存解決は [pyproject.toml](../apps/api/pyproject.toml) と [uv.lock](../apps/api/uv.lock) に固定。FastAPIのstandard extrasや外部へのデプロイツールは導入していない。AWSの配信・Lambda変換アダプターはDay 22〜23で選定・検証する。

## ファイルと責務

すべて`apps/api/src/sales_manager_api/`配下。

| ファイル | 担当 |
| --- | --- |
| `app.py` | アプリ生成、匿名のヘルスチェック、ハンドラー・ミドルウェア登録 |
| `settings.py` | 明示した設定ファイルとOS環境変数の読込、環境境界の検証 |
| `schemas.py` | 厳格な共通モデル、Health・Error応答の形 |
| `errors.py` | HTTP・入力検証・アプリ例外を共通エラーへ変換 |
| `middleware.py` | 要求UUID、応答ヘッダー、予期しない例外の500応答、最小限のログ |
| `__main__.py` | CLI引数、設定エラーでの起動停止、Uvicorn実行 |

## 設定の読込

優先順は**OS環境変数 → 明示したdotenv → 既定値**。設定はアプリ生成時に読む。`--env-file`を省略するとdotenvを読み込まない。既存ファイルの自動書換えや、呼出元シェルの環境変数変更は行わない。[Pydantic Settings公式](https://docs.pydantic.dev/latest/concepts/pydantic_settings/)

| 設定 | 値・条件 |
| --- | --- |
| `APP_ENV` | local / test / aws。既定local。不明な値は拒否 |
| `LOG_LEVEL` | DEBUG / INFO / WARNING / ERROR / CRITICAL。既定INFO |
| `AWS_REGION` | 既定ap-northeast-1。awsモードでは明示が必要。形式を検証し、実在リージョンの照会は行わない |
| `AWS_ENDPOINT_URL` | local/testでは未指定時127.0.0.1:4566、明示する場合はHTTPの127.0.0.1/localhost:4566のみ。末尾の`/`は1個だけ許容 |

local/testの空URL、実AWS URL、資格情報入りURL、他ポート、パス、クエリ、fragmentは拒否する。awsモードはリージョンを必須にし、URLの指定は空文字を含めて拒否する。dotenvの未知キーも拒否する。OS環境全体の未知キーを拒否する機能ではない。

見本は [apps/api/.env.example](../apps/api/.env.example)。これをそのまま`--env-file`で読むか、既存設定を上書きせずにローカル設定へコピーして使う。Day 2のAPP_ENV・LOG_LEVELだけのローカル設定もlocalモードの既定値で利用できる。

設定不正・指定ファイル不在はCLIが終了コード2で停止する。値や例外全文をそのまま表示せず、確認する設定名を案内する。設定を検証しても、**Day 5ではAWSクライアントを作成・接続しない**。SDKの資格情報・接続先の隔離と保存層はDay 6の実装対象。

## ヘルスチェックと仕様

`GET /health`は200と`{"status":"ok"}`を返す。認証情報とMiniStackの稼働を必要としない。これはプロセスの生存確認であり、データベース接続・Cognitoログイン・AWSへの配備成功を表すものではない。

APIのURL・入力条件・応答形式をまとめた仕様書は [openapi.yaml](contracts/openapi.yaml) で管理する。仕様書はYAMLで記述し、API応答のデータはJSONで返す。Day 5では自動OpenAPI URL・Swagger UI・ReDocを無効にし、API仕様書をこのYAMLに一本化する。`/docs`と`/openapi.json`も他の未実装パスと同じ404になる。

Day 5でYAMLへ追加したのは、共通500応答と`X-Request-ID`ヘッダー。全15操作の設計は維持し、実装済みルートはhealthだけと明記する。実装のHealth・Error応答はYAMLのスキーマと照合する。

## 共通エラーと要求ID

| 場面 | HTTP・code |
| --- | --- |
| 未実装・不明なパス | 404 / NOT_FOUND |
| 対応しないメソッド | 405 / METHOD_NOT_ALLOWED。Allowを保持 |
| 壊れたJSON | 400 / INVALID_JSON |
| 入力モデルの違反 | 422 / VALIDATION_ERROR |
| 明示したアプリ例外 | 例外に指定したステータス・公開コード・公開メッセージ |
| 応答開始前の予期しない例外 | 500 / INTERNAL_ERROR |

エラー本文は`error.code / message / request_id / details`。detailsの各要素は`path / code / message`だけで、入力値・例外context・スタックをそのまま含めない。HTTPExceptionの内部detailも公開しない。アプリ例外に渡すメッセージには、公開してよい文だけを指定する。[FastAPIの例外処理](https://fastapi.tiangolo.com/tutorial/handling-errors/)

要求ごとにサーバーがUUIDを生成し、`X-Request-ID`へ入れる。エラー本文のrequest_idと同じ値になる。クライアントが同名ヘッダーを送っても採用しない。

アプリの要求ログは要求ID・HTTPメソッド・ステータス、失敗時は例外の型名だけを記録する。本文・Authorization・URL・クエリ・例外メッセージは記録しない。CLIはUvicornのアクセスログも無効にする。LOG_LEVEL=DEBUGでもFastAPIのdebugはFalseに固定する。

応答開始後の例外は既に送ったステータスを500 JSONへ置き換えられないため、元の例外メッセージを隠した例外を再送出する。ストリーミング機能は今回実装していない。

## 確認範囲と後続Day

39件のテストで設定の優先順位・境界、Health/Errorスキーマ、入力・メソッド・不明パス・例外、要求ID、秘密の値を返さないこと、CLI起動条件を確認する。400/422/401/409/500の試験用ルートはテスト内だけで追加し、製品アプリへ登録しない。401の応答形式を確認しても認証そのものの実装完了とは扱わない。[FastAPIのテスト](https://fastapi.tiangolo.com/tutorial/testing/)

起動手順は [DAY5_COMMANDS.md](DAY5_COMMANDS.md)、実施結果は [DAY5_REVIEW.md](DAY5_REVIEW.md)。次はDay 6でSDKクライアント境界と保存層を作る。認証・CORS・クラウド公開・負荷試験は該当Dayで行う。
