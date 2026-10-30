# ローカル開発環境

作成・公式資料確認日：2026-10-29（Asia/Tokyo）。Day 2ではNext.jsの起動とPythonパッケージの実行までを用意する。LocalStackの起動はDay 3、HTTP APIはDay 5、画面とAPIの接続はDay 11で扱う。

Day 3の比較後はMiniStackでローカルAWS環境を構築した。起動・停止・検証専用の仮想環境・状態保持は [LOCAL_AWS.md](LOCAL_AWS.md)、検証結果は [DAY3_REVIEW.md](DAY3_REVIEW.md) を参照する。この手順書のNext.js・アプリPythonの採用版と依存関係はDay 2から変更しない。

Day 4の契約・保存設計の検証は [DAY4_REVIEW.md](DAY4_REVIEW.md) を参照する。追加した任意の`contracts`依存グループはローカルAWS検証専用で、アプリの依存は変更していない。

2026-10-30のDay 5更新：Python CLIはHTTPサーバーを起動する。FastAPIの採用・設定・共通エラーは [API_FOUNDATION.md](API_FOUNDATION.md)、コマンドと意味は [DAY5_COMMANDS.md](DAY5_COMMANDS.md)、結果は [DAY5_REVIEW.md](DAY5_REVIEW.md) を参照する。Day 2当時の起動確認記事は履歴として保持する。

## 採用バージョン

| 対象 | 固定したバージョン | 管理するファイル |
| --- | --- | --- |
| Node.js | 24.22.2（LTS） | ルートの `.nvmrc` |
| npm | 11.19.1（上記Node.jsに同梱） | `apps/web/package.json` の `packageManager` |
| Next.js | 16.4.3 | `apps/web/package.json`・`package-lock.json` |
| React / React DOM | 19.3.1 | 同上 |
| TypeScript | 6.0.3 | 同上 |
| Biome | 2.6.4 | 同上・`apps/web/biome.json` |
| Python | 3.14.9 | `apps/api/.python-version` |
| uv / uv_build | 0.13.6 | `apps/api/pyproject.toml` |
| Ruff | 0.17.3 | `apps/api/pyproject.toml`・`uv.lock` |
| FastAPI / Starlette / Uvicorn | 0.162.0 / 1.10.0 / 0.54.0 | 同上 |
| Pydantic / pydantic-settings | 2.14.2 / 2.16.2 | 同上 |
| pytest / HTTPX2 | 9.2.0 / 2.16.0 | 同上、devグループ |

直接依存はバージョンを完全指定し、間接依存はロックファイルに記録する。`packageManager` はnpmを自動で切り替える設定ではないため、`npm --version` も確認する。Pythonは3.14系を要件とし、普段の開発・検証では `.python-version` のパッチ版を使う。

採用時にはNode.js公式の配布情報、npm・PyPIの公開メタデータと公式資料を確認した。確認時点の採用版であり、将来の最新版を示す表ではない。更新は別の差分として検証・レビューする。

## ディレクトリと依存管理

```text
sales-manager-dashboard/
├── .nvmrc
├── apps/
│   ├── web/                 # Next.js / TypeScript
│   │   ├── package.json
│   │   ├── package-lock.json
│   │   ├── .env.example
│   │   └── src/app/
│   └── api/                 # Pythonパッケージ。HTTP APIはDay 5
│       ├── .python-version
│       ├── pyproject.toml
│       ├── uv.lock
│       ├── .env.example
│       └── src/sales_manager_api/
├── docs/
└── qiita/
```

npmは `apps/web/`、uvは `apps/api/` で依存を管理する。リポジトリ全体をnpm workspaceにはしていない。以下のコマンドはすべてプロジェクトルートで実行する。

## 1. 実行環境を準備する

Node.jsは [公式配布](https://nodejs.org/en/download) または利用中のバージョン管理ツールで24.22.2を導入する。[nvm](https://github.com/nvm-sh/nvm) を導入済みの場合は、ルートで次のように切り替えられる。

```sh
nvm install
nvm use
node --version
npm --version
```

期待値は `v24.22.2` と `11.19.1`。今回の検証では、macOS ARM64向け公式アーカイブのSHA-256を公式 `SHASUMS256.txt` と照合し、Git除外の `.tools/` に展開した。nvm自体の導入・実行と他のOSでの検証は行っていない。

uvは [公式導入手順](https://docs.astral.sh/uv/getting-started/installation/) に従って0.13.6を導入する。すでにPython 3.8以上がある環境では、プロジェクト内に専用の導入先を用意する方法も使える。以下は今回検証した配置方法である。

```sh
python3 -m venv .tools/uv
.tools/uv/bin/python -m pip install uv==0.13.6
export PATH="$PWD/.tools/uv/bin:$PATH"
uv --version
```

Python 3.14.9がなければ、uvで取得できる。ここでは管理先と実行ファイルの配置先をプロジェクト内に限定する。PATHの追加と以下の環境変数は、そのターミナルでの設定である。

```sh
export UV_PYTHON_INSTALL_DIR="$PWD/.tools/python"
export UV_PYTHON_BIN_DIR="$PWD/.tools/bin"
uv python install 3.14.9
```

## 2. ロックファイルから依存を導入する

```sh
npm --prefix apps/web ci
uv sync --project apps/api --locked
uv run --project apps/api --locked python --version
```

`npm ci` は既存の `package-lock.json` から導入する。`uv sync --locked` は `pyproject.toml` と `uv.lock` の整合性を検査し、不一致があればロックを無断で更新せず失敗する。通常の再導入で `npm install` や `uv lock` に置き換えない。

## 3. ローカル用設定を用意する

初回のみ、コピー先が存在しないことを確認して実行する。既存のローカル設定を上書きしない。

```sh
cp -n apps/web/.env.example apps/web/.env.local
cp -n apps/api/.env.example apps/api/.env
```

- `apps/web/.env.local`：Next.js用。`API_BASE_URL` はDay 11のサーバー側通信で使う予定の見本で、Day 2にはAPI通信を実装していない。
- `apps/api/.env`：Python用の任意設定。Day 5からCLIの`--env-file`で指定した場合に読み込む。OS環境変数が優先。見本を直接指定してもよい。
- 見本にはローカル接続先とダミーの設定だけを置く。実際のトークン・メール・売上データは含めない。
- `NEXT_PUBLIC_` 付きの値はブラウザーへ公開されるため、秘密情報を入れない。

## 4. 起動と停止

```sh
npm --prefix apps/web run dev
```

ブラウザーで `http://127.0.0.1:3000` を開く。「売上管理システム」「Next.jsの起動を確認できました。」が表示される。開発サーバーは127.0.0.1に限定し、終了は起動したターミナルで `Ctrl+C`。3000番が使用中なら `npm --prefix apps/web run dev -- --port 3001` のように指定する。

別のターミナルで、Pythonパッケージを実行する。

```sh
uv run --project apps/api --locked sales-manager-api --env-file apps/api/.env.example
```

Day 5からは127.0.0.1:8000でHTTPサーバーが起動する。別のターミナルの`curl -i http://127.0.0.1:8000/health`で200とstatus=okを確認し、起動側でCtrl+Cを押して停止する。MiniStackや実AWSへは接続しない。ポート変更・異常系はDay 5のコマンド解説を参照する。

## 5. 変更を検証する

```sh
npm --prefix apps/web run lint
npm --prefix apps/web run typecheck
npm --prefix apps/web run build
uv run --project apps/api --locked pytest apps/api/tests -q
uv run --project apps/api --locked ruff check apps/api
uv run --project apps/api --locked ruff format --check apps/api
uv lock --project apps/api --check
git diff --check
```

`lint` はBiomeによる静的検証・書式確認、`typecheck` はNext.jsの型生成とTypeScriptのチェックを行う。書式の修正には `npm --prefix apps/web run format` を使う。本番ビルドはlintとは別に実行する。

本番モードを確認する場合は、開発サーバーを停止してから以下を実行する。停止方法は開発時と同じ。

```sh
npm --prefix apps/web run start
```

`node_modules/`、`.next/`、`.venv/`、`.tools/`、キャッシュ、ローカルの `.env` はGitへ登録しない。`.env.example` とロックファイルは登録する。

検証結果・未確認事項・共有するレビュー状況は [DAY2_REVIEW.md](DAY2_REVIEW.md) を参照する。PR・タグはGitHubで確認し、個人環境の詳細な操作履歴はローカル専用台帳で管理する。

## 参照資料

- [Next.js：インストールと実行コマンド](https://nextjs.org/docs/app/getting-started/installation)
- [Next.js：環境変数](https://nextjs.org/docs/app/guides/environment-variables)
- [Node.js：サポートされるリリース](https://nodejs.org/en/about/previous-releases)
- [Python：バージョンのサポート状況](https://devguide.python.org/versions/)
- [uv：プロジェクト管理](https://docs.astral.sh/uv/guides/projects/)
- [uv：ロックと同期](https://docs.astral.sh/uv/concepts/projects/sync/)
- [Biome：導入と静的検証](https://biomejs.dev/installation/quick-start/)
- [Ruff：導入と実行](https://docs.astral.sh/ruff/installation/)
