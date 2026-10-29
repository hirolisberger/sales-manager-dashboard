# 【Day 02】Next.jsとPythonを同じリポジトリで育てる開発環境づくり

シリーズ：**Next.js・Python・LocalStack・AWSで作る売上管理システム**

公開予定：2026年12月2日（日本時間）。開発・レビューとQiitaへの公開は別に管理しています。

## はじめに

Day 1では、小規模店舗の商品別売上管理について要件と全体設計を整理しました。Day 2は、Next.jsとPythonの開発環境を同じリポジトリに用意します。

前回の内容は [Day 1：要件定義と全体設計（GitHub上の原稿）](https://github.com/hirolisberger/sales-manager-dashboard/blob/3b4292f901f7e3553c5a19a9e286304348b4810b/qiita/day01-requirements-and-architecture.md) を参照してください。

今回の到達点は、依存関係を再導入でき、Next.jsの確認用ページとPythonパッケージを実行できることです。商品登録や売上登録、HTTP API、LocalStackへの接続は、後続の記事で作ります。

リポジトリは [sales-manager-dashboard](https://github.com/hirolisberger/sales-manager-dashboard) です。完成版は [`day02` タグ](https://github.com/hirolisberger/sales-manager-dashboard/tree/day02) で案内します。タグはレビュー承認とmainへのマージ後に作成するため、Qiita公開前に参照先を確認します。

## この記事の到達点

- Next.jsとPythonの配置・依存管理を分ける
- 実行環境と依存パッケージのバージョンを記録する
- ロックファイルから依存を導入し、起動と静的検証を行う
- 共有する設定見本と、ローカルだけで保持する設定を分ける

公式資料・公開パッケージ情報の確認日は2026年10月29日です。検証環境はmacOS・Apple Siliconです。

## 1. 実行環境と配置を決める

今回の主な採用バージョンは次のとおりです。

| 対象 | 採用バージョン |
| --- | --- |
| Node.js / npm | 24.22.2 / 11.19.1 |
| Next.js | 16.4.3 |
| React / React DOM | 19.3.1 |
| TypeScript | 6.0.3 |
| Biome | 2.6.4 |
| Python | 3.14.9 |
| uv / uv_build | 0.13.6 |
| Ruff | 0.17.3 |

Node.jsはLTSの24系を選び、`.nvmrc` にパッチ版まで記録しました。Next.jsの必要条件を満たすことを公式資料で確認し、実際に型チェックとビルドを行います。将来の最新版を自動で使う構成にはしません。[Node.js公式のリリース案内](https://nodejs.org/en/about/previous-releases)、[Next.js公式の導入手順](https://nextjs.org/docs/app/getting-started/installation)

```text
sales-manager-dashboard/
├── .nvmrc
├── apps/
│   ├── web/
│   │   ├── package.json
│   │   ├── package-lock.json
│   │   ├── .env.example
│   │   └── src/app/
│   └── api/
│       ├── .python-version
│       ├── pyproject.toml
│       ├── uv.lock
│       ├── .env.example
│       └── src/sales_manager_api/
├── docs/
└── qiita/
```

同じリポジトリでも、依存管理は別々です。フロントエンドは `apps/web/` のnpm、Pythonは `apps/api/` のuvで管理します。全体をnpm workspaceにせず、それぞれの導入・実行コマンドが分かる構成にしました。

以下のコマンドは、すべて `sales-manager-dashboard/` のルートで実行します。

## 2. Node.jsとuv・Pythonを用意する

Node.js 24.22.2を公式配布や利用中のバージョン管理ツールで導入します。すでに [nvm](https://github.com/nvm-sh/nvm) を使っていれば、ルートの `.nvmrc` を利用できます。

```sh
nvm install
nvm use
node --version
npm --version
```

期待値は `v24.22.2` と `11.19.1` です。今回はnvmではなく、公式のmacOS ARM64用アーカイブをSHA-256で照合して利用しました。nvm自体の導入と他OSでの動作は未検証です。

uvはPythonの依存管理に使います。Python 3.8以上がすでにあれば、次のように専用の仮想環境へ固定版を導入できます。`.tools/` はGitから除外します。[uv公式の導入手順](https://docs.astral.sh/uv/getting-started/installation/)

```sh
python3 -m venv .tools/uv
.tools/uv/bin/python -m pip install uv==0.13.6
export PATH="$PWD/.tools/uv/bin:$PATH"
uv --version
```

ここで使った `python3` はuvを導入するためのPythonです。アプリケーション用は `.python-version` に記録した3.14.9を使います。未導入ならuvで取得します。管理先をプロジェクト内に指定する例です。[uv公式のPython導入手順](https://docs.astral.sh/uv/guides/install-python/)

```sh
export UV_PYTHON_INSTALL_DIR="$PWD/.tools/python"
export UV_PYTHON_BIN_DIR="$PWD/.tools/bin"
uv python install 3.14.9
```

PATHやこれらの環境変数は、設定したターミナルで有効になります。

## 3. ロックファイルから依存をそろえる

リポジトリには、直接依存を完全指定した `package.json` と `pyproject.toml`、間接依存も記録する `package-lock.json` と `uv.lock` を置きます。読者が導入するときには、既存のロックを使います。

```sh
npm --prefix apps/web ci
uv sync --project apps/api --locked
uv run --project apps/api --locked python --version
```

Pythonの出力は `Python 3.14.9` です。`uv sync --locked` はロックと設定の整合性を検査し、不一致なら失敗します。再導入のつもりでロックファイルを更新しないことがポイントです。[uv公式のロック・同期の説明](https://docs.astral.sh/uv/concepts/projects/sync/)

Next.jsはApp Router、TypeScript、通常のCSSを使った確認用ページにしました。外部フォントの取得は必要ありません。静的検証と書式はBiome、Python側はRuffで確認します。[Biome公式の導入手順](https://biomejs.dev/installation/quick-start/)、[Ruff公式の導入手順](https://docs.astral.sh/ruff/installation/)

PythonにはまだFastAPIなどのHTTPフレームワークを入れていません。Day 5でAPIの土台を作るときに確定します。Day 2ではパッケージと実行入口を用意し、依存管理が機能することを確認します。

## 4. 設定の見本を共有する

`.env.example` を共有し、実際に使うローカル設定はGitから除外します。初回のみ、コピー先がないことを確認して実行します。

```sh
cp -n apps/web/.env.example apps/web/.env.local
cp -n apps/api/.env.example apps/api/.env
```

Web側の見本は次のとおりです。

```dotenv
API_BASE_URL=http://127.0.0.1:8000
```

これはDay 11で使う予定のサーバー側接続先で、今回はAPI通信を行いません。Python側は `APP_ENV=local` と `LOG_LEVEL=INFO` の見本だけを用意し、設定の読み込みと検証はDay 5で実装します。

Next.jsでは `NEXT_PUBLIC_` 付きの環境変数がブラウザーへ公開されます。APIの秘密情報やAWSの認証情報を入れないようにします。[Next.js公式の環境変数の説明](https://nextjs.org/docs/app/guides/environment-variables)

`.env.example`、ロックファイル、ソースコードを登録し、`.env.local`、`.env`、`node_modules/`、`.next/`、`.venv/`、`.tools/` は登録しません。

## 5. Next.jsとPythonの起動を確認する

Next.jsの開発サーバーを起動します。

```sh
npm --prefix apps/web run dev
```

`http://127.0.0.1:3000` を開くと、「売上管理システム」「Next.jsの起動を確認できました。」を表示するページを返します。開発サーバーは127.0.0.1に限定しました。停止は起動したターミナルで `Ctrl+C` です。

別のターミナルでPythonの確認用コマンドを実行します。

```sh
uv run --project apps/api --locked sales-manager-api
```

```text
sales-manager-api: development environment is ready.
```

これはメッセージを出して終了するコマンドです。HTTPサーバーやヘルスチェックはまだありません。パッケージが導入され、実行入口を解決できたことを確認しています。

## 6. 完成前に実行するチェックをそろえる

```sh
npm --prefix apps/web run lint
npm --prefix apps/web run typecheck
npm --prefix apps/web run build
uv run --project apps/api --locked ruff check apps/api
uv run --project apps/api --locked ruff format --check apps/api
uv lock --project apps/api --check
git diff --check
```

`typecheck` は `next typegen` を実行してから `tsc --noEmit` を実行します。Next.jsの型生成を先に行うことで、まだビルドしていない環境でも型チェックできるようにしました。lintと本番ビルドは別々のチェックとして実行します。[Next.js公式の実行・lint設定](https://nextjs.org/docs/app/getting-started/installation)

本番モードは、開発サーバーを停止し、本番ビルドが成功してから起動します。

```sh
npm --prefix apps/web run start
```

今回の確認結果は [Day 2の検証記録](https://github.com/hirolisberger/sales-manager-dashboard/blob/day02/docs/DAY2_REVIEW.md) に残します。コード・設定の詳細は [開発環境の手順](https://github.com/hirolisberger/sales-manager-dashboard/blob/day02/docs/DEVELOPMENT.md) を参照してください。これらも完成版タグの反映後に有効になるリンクです。

## 今回の確認結果

| 確認 | 結果 |
| --- | --- |
| npm / uvのロックからの導入 | 成功。再導入前後で両ロックファイルのSHA-256が一致 |
| Biome・TypeScript・Next.js本番ビルド | すべて成功 |
| Next.jsの開発・本番モード | HTTP 200、日本語設定、見出しと起動確認メッセージを確認 |
| 存在しないページ | 本番モードでHTTP 404を確認 |
| Pythonパッケージの実行・Ruff・配布物作成 | すべて成功。配布物の外部公開はしていない |
| npmの依存監査 | 確認時点で脆弱性の検出0件 |
| 文書とGit除外 | ローカル文書リンク、シェル例の構文、記事の匿名化、ローカル設定・生成物の除外を確認 |

HTTPの応答確認は、ブラウザーでの描画・操作のE2Eテストとは別です。今回はmacOS ARM64で検証し、他OSとブラウザー描画は未検証として残しました。売上の業務機能やHTTP APIのテストは、実装するDayで追加します。

## まとめと次回

同じリポジトリにNext.jsとPythonを配置し、実行環境・依存関係・設定見本・検証コマンドをそろえました。今回は起動と依存管理の土台を作った段階で、売上管理の業務機能はこれから実装します。

開発は `feature/day02` で進め、検証結果と記事をPRでレビューします。レビュー承認後にmainへマージし、完成版の `day02` タグを共有します。Qiitaへの投稿・公開は別に管理します。

次回のDay 3では、LocalStackの起動・接続とローカル用の環境分離を整えます。Day 2のレビュー承認前には着手しません。
