# Day 2：開発環境の確認とレビュー資料

確認日：2026-10-29（Asia/Tokyo）。ブランチ：`feature/day02`。基点：main / origin/main `4295718`。

## 対象と範囲

- `apps/web/`：Next.js / TypeScriptの確認用ページ、Biome設定、npmロックファイル。
- `apps/api/`：Pythonパッケージ、実行入口、uv・Ruff設定、Pythonと依存の固定。
- `.nvmrc`、`.gitignore`、両アプリの `.env.example`。
- [開発環境の手順](DEVELOPMENT.md)、[Day 2記事](../qiita/day02-nextjs-python-development-environment.md)、関連する進捗と運用ルール。

Day 1は開発・検証・レビュー承認・mainへのマージ・pushを完了している。残る資料リンクの公開用URLへの置換、Mermaidの表示確認、任意のDay 1タグ付与は公開準備として別管理する。今回の条件付き開始指示をDay 2への着手指示として記録する。

直前の会話で合意したPR・タグ運用の未コミット変更3ファイルを保持し、Day 2のブランチへ引き継いだ。Day 1の記事・設計内容は変更しない。

## 検証記録

macOS ARM64、Node.js 24.22.2、npm 11.19.1、Python 3.14.9、uv 0.13.6を使用。Node.jsは公式配布アーカイブをSHA-256で照合し、Git除外の `.tools/` へ配置した。Pythonの既存環境での依存導入と、uvによる3.14.9の取得を確認する。

| 確認 | コマンド・方法 | 結果 |
| --- | --- | --- |
| npmロック作成後の再導入 | `npm --prefix apps/web ci`（検証では既取得キャッシュを指定してオフライン実行） | 成功。既存のnode_modulesをロックから再導入 |
| Pythonの依存導入 | `uv sync --project apps/api --locked` | 成功。専用 `.venv` にロック済み依存とパッケージを導入 |
| Webの静的検証・書式 | `npm --prefix apps/web run lint` | 成功。Biomeで7ファイルを確認 |
| Webの型 | `npm --prefix apps/web run typecheck` | 成功。Next.js型生成とTypeScriptチェック |
| 本番ビルド | `npm --prefix apps/web run build` | 成功。`/` とnot-foundページを静的生成 |
| Web開発モード | HTTPで `/` のステータス、HTMLのlang・見出し・本文を確認 | 成功。HTTP 200、lang=ja、見出し・確認メッセージが一致。確認後に停止 |
| Web本番モード | ビルド後に起動し、同じHTMLと存在しないパスの404を確認 | 成功。HTTP 200・本文一致、存在しないパスは404。確認後に停止 |
| Pythonの実行 | `uv run --project apps/api --locked sales-manager-api` | 成功。`sales-manager-api: development environment is ready.` を出力して終了 |
| Pythonの版 | `uv run --project apps/api --locked python --version` | `Python 3.14.9` |
| Pythonの静的検証・書式 | `uv run --project apps/api --locked ruff check apps/api` と `ruff format --check apps/api` | 成功。lint・書式とも問題なし |
| Pythonの配布物 | `uv build --project apps/api --out-dir .cache/api-dist` | 成功。sdistとwheelを生成。配布・公開はしていない |
| uvロックの整合性 | `uv lock --project apps/api --check` | 成功 |
| npmの脆弱性監査 | `npm --prefix apps/web audit` | 確認時点で0件。将来の安全性を保証するものではない |
| 再導入前後のロック | SHA-256で両ロックファイルの一致を比較 | 成功。npm ciとuv sync --lockedで変更なし |
| Git除外・文書・記事 | `.env.example` とロックは登録対象、ローカル設定・依存・生成物は除外。文書リンク・Markdown・記事内シェル構文・匿名化・`git diff --check` | 成功。17文書・97ローカルリンク・35シェル例を確認。秘密情報パターン、ロック内の個人パス・認証付きURLも検査 |

HTTP確認はブラウザー描画やユーザー操作のE2Eテストではない。確認用ページの見た目はユーザーレビューで確認する。業務機能のテストやHTTP APIのテストはまだ存在しない。

検証用の実行環境では最初のlistenが権限制限で失敗したため、127.0.0.1:3000への一時起動を許可した環境で再実行した。アプリケーションのコード修正は不要だった。Python取得時の実行ファイルリンクも `.tools/bin/` へまとめ、既存のNode.js・Pythonの設定は変更していない。

Next.js 16.4.3の開発サーバーが生成した `apps/web/AGENTS.md` は追跡対象に含める。ルートの運用ルールに加え、Next.js同梱の最新版資料を参照するための補足として扱う。

## レビューで確認してほしいこと

1. Node.js 24系LTS・Python 3.14系と、npm / uvをそれぞれ使用する配置・依存管理。
2. 手順に沿ってNext.jsの確認用ページとPythonの実行メッセージを確認できること。
3. `.env.example` 以外のローカル設定・依存・生成物をGitへ含めないこと。
4. Day 2記事が実装済みの範囲を説明し、LocalStack・HTTP API・業務機能を後続Dayとしていること。
5. レビュー承認後にPRをマージし、完成版タグを共有する運用。

## 未確認事項と後続Day

- nvmの導入・実行、Windows / Linuxでの起動、ブラウザーでの描画：未検証。
- LocalStack・Dockerの起動とAWS接続：Day 3以降。今回は実行していない。
- FastAPI等のフレームワーク、HTTP API、設定読込、APIテスト：Day 5。
- WebとAPIの通信：Day 11。
- GitHubでのPR作成：接続方法を確認中。GitHubプラグインの追加・アカウント接続が必要。featureのpushとPR作成は別に結果を記録する。
- `day02` タグ：レビュー承認・PRマージ前のため未作成。記事のタグURLは公開前に有効性を確認する。
- Qiitaへの投稿・更新・予約登録：未実施。予定日は2026-12-02のまま維持する。

レビュー・PR・タグの実績と対象コミットは [PROGRESS.md](PROGRESS.md) に記録する。Day 3はDay 2のレビュー承認とユーザーの開始指示を受けてから着手する。
