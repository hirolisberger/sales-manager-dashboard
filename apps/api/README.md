# sales-manager-api

Day 5でFastAPI・Uvicornによるhealth・設定読込・共通エラー・要求ID、Day 6でDynamoDBクライアント・保存層・初期化CLI、Day 7で商品4操作、Day 8で売上登録、Day 9で検索・詳細・期間/商品/状態検索・ページング、Day 10で訂正・取消・履歴を追加しました。計11操作です。商品・売上APIはlocal/test専用で、認証・集計・CSVは後続Dayです。

プロジェクトルートから実行します。Pythonの指定は [.python-version](.python-version)、依存関係は [pyproject.toml](pyproject.toml) と [uv.lock](uv.lock) で管理します。

```sh
uv sync --project apps/api --locked
uv run --project apps/api --locked sales-manager-api --env-file apps/api/.env.example
```

別のターミナルで確認します。

```sh
curl -i http://127.0.0.1:8000/health
curl -i http://127.0.0.1:8000/missing
curl -i -X POST http://127.0.0.1:8000/health
```

順に200・404・405を返します。停止は起動したターミナルで`Ctrl+C`。healthの確認だけならMiniStackの起動は不要です。商品APIの確認はMiniStackと初期化済みテーブルが必要です。Day 2までの同名コマンドはメッセージを出して終了しましたが、現在はHTTPサーバーを起動します。

```sh
uv run --project apps/api --locked pytest apps/api/tests -q
uv run --project apps/api --locked ruff check apps/api
uv run --project apps/api --locked ruff format --check apps/api
```

CLIは`127.0.0.1`だけで待ち受けます。`--port 8001`でポートを変更できます。`.env`の読込は明示的な`--env-file`指定が必要で、OS環境変数を優先します。設定の見本は [.env.example](.env.example)、API仕様書は [openapi.yaml](../../docs/contracts/openapi.yaml) です。

詳しい手順と各指定の意味は [DAY5_COMMANDS.md](../../docs/DAY5_COMMANDS.md)、設定・エラーの仕様は [API_FOUNDATION.md](../../docs/API_FOUNDATION.md)、確認結果は [DAY5_REVIEW.md](../../docs/DAY5_REVIEW.md) を参照してください。採用バージョンとフロント環境は [DEVELOPMENT.md](../../docs/DEVELOPMENT.md) に記録しています。

保存層の仕様は [PERSISTENCE.md](../../docs/PERSISTENCE.md)、MiniStack起動・データ初期化・各コマンドの意味は [DAY6_COMMANDS.md](../../docs/DAY6_COMMANDS.md)、結果は [DAY6_REVIEW.md](../../docs/DAY6_REVIEW.md) を参照してください。`sales-manager-data`はlocal/test専用で、API起動時に自動で実行されません。

商品APIの仕様は [PRODUCT_API.md](../../docs/PRODUCT_API.md)、起動からcurlの各指定までの手順は [DAY7_COMMANDS.md](../../docs/DAY7_COMMANDS.md)、結果は [DAY7_REVIEW.md](../../docs/DAY7_REVIEW.md) を参照してください。

訂正・取消・履歴の仕様は[SALE_CHANGES.md](../../docs/SALE_CHANGES.md)、全コマンド解説は[DAY10_COMMANDS.md](../../docs/DAY10_COMMANDS.md)、結果は[DAY10_REVIEW.md](../../docs/DAY10_REVIEW.md)を参照してください。
