# sales-manager-api

Python API用パッケージの配置と依存管理を用意した段階です。Day 2のコマンドはPython環境の起動確認用で、HTTPサーバーは起動しません。APIフレームワーク・ヘルスチェック・設定読込・APIテストはDay 5で実装します。

プロジェクトルートから実行します。Pythonの指定は [.python-version](.python-version)、依存関係は [pyproject.toml](pyproject.toml) と [uv.lock](uv.lock) で管理します。

```sh
uv sync --project apps/api --locked
uv run --project apps/api --locked sales-manager-api
uv run --project apps/api --locked ruff check apps/api
uv run --project apps/api --locked ruff format --check apps/api
```

導入方法と採用バージョンは [開発環境の手順](../../docs/DEVELOPMENT.md) を参照してください。
