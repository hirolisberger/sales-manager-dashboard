# 【Day 05】Python APIの土台を作る：FastAPI・設定・共通エラー・テスト

シリーズ：**Next.js・Python・AWSで作る売上管理システム**

公開予定：2026年12月5日（日本時間）。開発・レビューとQiitaへの公開は別に管理しています。

## はじめに

[Day 4](https://github.com/hirolisberger/sales-manager-dashboard/blob/day04/qiita/day04-data-model-and-api-contract.md)では、売上のデータモデルとAPI仕様を決めました。今回はPythonでHTTP要求を受け付ける土台を作ります。

**実装するのは`GET /health`、設定読込、共通エラー、要求ID、起動CLIとテストです。** 商品登録や売上保存、認証は後続Dayで追加します。まず正常時と失敗時に何を返すかをそろえ、実装を増やす前に確認できる状態にします。

## この記事の到達点

- FastAPIとUvicornでローカルHTTP APIを起動する
- 設定ファイルと環境変数の優先順を決める
- ローカルとAWSの接続設定を混ぜない入力条件を設ける
- エラー形式と要求IDをそろえ、設計YAMLとテストで照合する

リポジトリは [sales-manager-dashboard](https://github.com/hirolisberger/sales-manager-dashboard) です。この回の完成版は [`day05`タグ](https://github.com/hirolisberger/sales-manager-dashboard/tree/day05) で共有する予定です。レビュー承認とmainマージ後に作成するため、現時点では未作成です。以降のday05文書リンクも公開前に存在を確認します。

確認日は2026-10-30。macOS ARM64、Python 3.14.9、uv 0.13.6で検証しました。

## 1. FastAPIとUvicornを採用する

APIフレームワークはFastAPI 0.162.0、ASGIサーバーはUvicorn 0.54.0を採用しました。モデルはPydantic 2.14.2、設定読込はpydantic-settings 2.16.2です。[FastAPI公式](https://fastapi.tiangolo.com/tutorial/first-steps/)

FastAPIに要求の振り分けと入力検証を任せ、業務ルールや保存処理は別のモジュールへ追加する方針です。アプリの生成は`create_app`にまとめ、サーバー起動とテストで同じ構成を使います。

```text
apps/api/src/sales_manager_api/
├── app.py          アプリ生成・health
├── settings.py     設定読込・検証
├── schemas.py      共通モデル
├── errors.py       共通エラー変換
├── middleware.py   要求ID・ログ・予期しない例外
└── __main__.py     CLI・サーバー起動
```

依存バージョンとuv.lockを固定し、パッケージの配布物も確認します。AWSへの配置方法とLambda向けの変換は、Day 22〜23で決めます。今回の起動成功をAWSでの動作確認とは扱いません。

## 2. まずプロセスの生存を確認する

`GET /health`は次のJSONを200で返します。

```json
{"status":"ok"}
```

MiniStackやAWSへ問い合わせない生存確認にしました。認証情報がなくても、ローカルAWS環境を停止していても、このAPIの起動を確認できます。データベースやCognitoが利用可能かを示すreadinessとは別の役割です。

公開するルートは現時点でhealthだけです。`/products`は404を返します。テスト用の例外発生ルートも製品アプリへは登録しません。

## 3. 設定を読む場所と優先順を決める

設定の優先順は次のとおりです。

```text
OS環境変数 → --env-fileで明示したファイル → 既定値
```

`--env-file`を省略するとdotenvを読みません。指定ファイルを読むときも、呼出元シェルの値や既存ファイルを変更しません。[Pydantic Settings公式](https://docs.pydantic.dev/latest/concepts/pydantic_settings/)

| 設定 | 主な意味 |
| --- | --- |
| APP_ENV | local / test / aws。既定local |
| LOG_LEVEL | ログレベル。既定INFO |
| AWS_REGION | リージョン。awsモードでは明示必須 |
| AWS_ENDPOINT_URL | local/testの接続先。未指定なら127.0.0.1:4566 |

local/testで明示できるURLは、HTTPの127.0.0.1またはlocalhostの4566番に限ります。空文字、実AWSのURL、資格情報入りURL、パスやクエリ、別ポートは拒否します。awsモードでは逆にURL上書きを拒否し、リージョンを明示させます。

たとえばAPP_ENVだけをawsに変え、ローカルのURLが残っている設定では起動させません。不正な設定を別の接続先へ読み替えて続行しない方針です。

ただし、Day 5は設定を検証するところまでです。AWS SDKクライアントの作成と資格情報の隔離、保存処理はDay 6で実装します。今回のアプリはAWSへ接続しません。

## 4. 失敗時のJSONをそろえる

エラーにはDay 4で決めた共通形式を使います。次は例です。

```json
{
  "error": {
    "code": "NOT_FOUND",
    "message": "対象が見つかりません。",
    "request_id": "00000000-0000-4000-8000-000000000090",
    "details": []
  }
}
```

| 場面 | HTTP・code |
| --- | --- |
| 不明なパス | 404・NOT_FOUND |
| 対応していないメソッド | 405・METHOD_NOT_ALLOWED |
| 壊れたJSON | 400・INVALID_JSON |
| 入力モデル違反 | 422・VALIDATION_ERROR |
| 応答開始前の予期しない例外 | 500・INTERNAL_ERROR |

入力検証とHTTP例外のハンドラーを登録します。入力値や例外contextを応答へそのまま入れず、予期しない例外のメッセージも返しません。405のAllowや401のWWW-Authenticateなど、HTTPの意味を持つヘッダーは保持します。[FastAPIの例外処理](https://fastapi.tiangolo.com/tutorial/handling-errors/)

要求ごとにサーバーがUUIDを作り、`X-Request-ID`へ入れます。エラー本文のrequest_idも同じ値なので、報告されたIDでログを照合できます。クライアントから同名のヘッダーを受け取っても、新しいIDを使います。

ログは要求ID・メソッド・ステータスと、失敗した例外の型名に絞りました。本文・Authorization・クエリ・例外メッセージは記録せず、CLIではUvicornのアクセスログも無効にしています。

## 5. API仕様書はYAMLで管理する

APIのURL、入力条件、応答形式をまとめた仕様書を、`docs/contracts/openapi.yaml`で管理しています。今回は、Day 4で作ったこの仕様書へ共通500応答と要求IDヘッダーを追加しました。

仕様書はYAMLで記述し、APIが通信で返すデータはJSONを使います。

今回のアプリでは自動OpenAPI URL・Swagger UI・ReDocを無効にしています。設計には将来の15操作がありますが、現時点で動くパスはhealthだけです。APIの応答モデルをテストし、読み込んだYAMLのHealth/Errorスキーマへ照合します。

JSON Schemaの構文検証だけで、HTTP実装の動作が保証されるわけではありません。壊れたJSON、厳格な整数、小数・bool・文字列の拒否などは、テスト内のルートを通して確認します。

## 6. 起動して確認する

プロジェクトルート`sales-manager-dashboard/`で実行します。プロジェクト内のuvを使う例です。PATH上のuvを使う場合は`.tools/uv/bin/uv`を`uv`へ置き換えます。

```sh
UV_CACHE_DIR="$PWD/.cache/uv" .tools/uv/bin/uv sync --project apps/api --locked

UV_CACHE_DIR="$PWD/.cache/uv" .tools/uv/bin/uv run \
  --project apps/api --locked \
  sales-manager-api --env-file apps/api/.env.example
```

設定見本を直接読むため、手元の`.env`を上書きせずに試せます。`sales-manager-api`はDay 2の確認メッセージ表示から、HTTPサーバーを起動し続けるコマンドへ変わりました。

起動したターミナルはそのままにし、別のターミナルで確認します。

```sh
curl -i http://127.0.0.1:8000/health
curl -i http://127.0.0.1:8000/missing
curl -i -X POST http://127.0.0.1:8000/health
```

順に200・404・405が返ります。`-i`で表示される`x-request-id`と、エラー本文のrequest_idが一致することも確認できます。ブラウザーで`http://127.0.0.1:8000/health`を開けば、正常時の本文を確認できます。

停止は起動したターミナルで`Ctrl+C`です。ポートが使用中なら起動コマンドへ`--port 8001`を付け、確認URLも8001へ変更します。

## 7. テストと実HTTPの結果

```sh
UV_CACHE_DIR="$PWD/.cache/uv" .tools/uv/bin/uv run \
  --project apps/api --locked pytest apps/api/tests -q
```

**39件が成功し、警告はありませんでした。** 設定の優先順位と境界、正常・異常応答、要求ID、内部の値を返さないこと、CLIが不正設定で停止することを確認しています。StarletteのTestClientを使うため、テスト用依存はHTTPX2 2.16.0に固定しました。[FastAPIのテスト](https://fastapi.tiangolo.com/tutorial/testing/)

400/422/401/409/500はテスト内だけに追加したルートで確認しています。401や409の形式が通っても、認証や重複送信制御の実装は完了していません。

実際にCLIを一時ポートで起動した確認でも、200・404・405と要求IDが一致しました。待受は127.0.0.1だけで、SIGINTで正常終了し、ポートが閉じたことも確認しました。

加えて、Ruff、更新したYAMLの既存6テストグループ、配布物の作成が成功しました。空の環境へロックから実行用依存だけを導入し、wheelをリポジトリ外から読み込めることも確認しています。テスト用ライブラリは実行用依存へ含めません。

詳しい[起動コマンドの解説](https://github.com/hirolisberger/sales-manager-dashboard/blob/day05/docs/DAY5_COMMANDS.md)、[設定とエラーの仕様](https://github.com/hirolisberger/sales-manager-dashboard/blob/day05/docs/API_FOUNDATION.md)、[検証記録](https://github.com/hirolisberger/sales-manager-dashboard/blob/day05/docs/DAY5_REVIEW.md)はday05タグ作成後に参照可能になります。

## まとめと次回

Day 5では、HTTP要求を受け付ける土台を作り、設定とエラーの扱いをそろえました。APIが返すJSONを設計YAMLへ照合し、起動から停止まで手元で確認できるようになりました。

この実装と記事のレビュー承認・mainマージ後、開始指示を受けてDay 6の保存層へ進みます。公開予定日は2026年12月5日で、投稿・予約操作は開発・レビューと別に管理します。
