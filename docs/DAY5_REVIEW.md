# Day 5：Python APIの土台とテスト

確認日：2026-10-30（Asia/Tokyo）。ブランチ`feature/day05`、基点main / day04：`eda0c85c9d2fd876f21a5110ea419c3a43c1ce52`。Day 4の承認・[PR #3](https://github.com/hirolisberger/sales-manager-dashboard/pull/3)マージ・注釈付きday04タグと最新mainの一致を確認して着手した。

**Day 5は実装・記事・必要なローカル確認が完了し、レビュー待ち。** Day 6へは承認・PRマージと別途の開始指示を受けるまで進めない。

## 成果物

- `apps/api/src/sales_manager_api/`：FastAPIの生成、設定読込、Health/Errorモデル、例外処理、要求IDミドルウェア、起動CLI。
- `apps/api/tests/`：設定・HTTP・CLIの39テスト。試験用ルートはテスト内だけに置く。
- `apps/api/pyproject.toml`・`uv.lock`・`.env.example`・`README.md`：固定依存・設定見本・起動手順。
- [OpenAPI YAML](contracts/openapi.yaml)：共通500と要求IDヘッダー。正本はYAMLに一本化。
- [API_FOUNDATION.md](API_FOUNDATION.md)：設定の優先順・境界・エラー・ログと後続Dayの範囲。
- [DAY5_COMMANDS.md](DAY5_COMMANDS.md)：起動・curl・自動テスト・停止と各指定の解説。
- [Day 5記事](../qiita/day05-fastapi-foundation-and-tests.md)、README・計画・開発ルールの更新。Day 4の確認記録へマージ・タグ情報を補完。

## 再現コマンド

プロジェクトルートで実行する。実行用のvenvは`apps/api/.venv/`。MiniStack・実AWS・実認証情報は使わない。

```sh
UV_CACHE_DIR="$PWD/.cache/uv" .tools/uv/bin/uv sync --project apps/api --locked

UV_CACHE_DIR="$PWD/.cache/uv" .tools/uv/bin/uv run \
  --project apps/api --locked pytest apps/api/tests -q

UV_CACHE_DIR="$PWD/.cache/uv" .tools/uv/bin/uv run \
  --project apps/api --locked ruff check --config apps/api/pyproject.toml apps/api scripts

UV_CACHE_DIR="$PWD/.cache/uv" .tools/uv/bin/uv run \
  --project apps/api --locked ruff format --check --config apps/api/pyproject.toml apps/api scripts
```

起動と手動のHTTP確認は[コマンド解説](DAY5_COMMANDS.md)のターミナルA/Bの手順を使う。実装したHealth/Errorと設計YAMLの一致はpytestでも確認する。契約全体は次で確認できる。

```sh
UV_CACHE_DIR="$PWD/.cache/uv" .tools/uv/bin/uv run \
  --project infra/local-aws --group contracts --locked \
  python scripts/verify_day04_contract.py
```

## 確認結果

環境：macOS ARM64、Python 3.14.9、uv 0.13.6。FastAPI 0.162.0、Starlette 1.10.0、Uvicorn 0.54.0、Pydantic 2.14.2、pydantic-settings 2.16.2、pytest 9.2.0、HTTPX2 2.16.0。

| 確認 | 結果 |
| --- | --- |
| API自動テスト | 39件成功、警告なし |
| 設定ファイル | 未指定時dotenvを自動読込しない。指定ファイルを読み、OS環境を優先。呼出プロセスの環境は変更しない |
| 環境境界 | 不明モード・不正リージョン形式・ローカルの外部URL/空URL/資格情報/パス/他ポートを拒否。awsでは明示リージョンが必要でURL指定を拒否 |
| 設定エラー | ファイル不在・未知dotenvキーを拒否。CLIは値を表示せず終了コード2で停止し、サーバーを起動しない |
| 生存確認 | GET /healthが200・status=ok。socket接続を禁止したテストと不正な個人AWS profileの環境でも成功 |
| 共通応答 | 404・405・400・422・401・409・500の形式と、Allow/WWW-Authenticateの保持を確認。試験用ルートは実アプリに存在しない |
| 厳格な入力 | テスト用モデルでbool・1.0・数値文字列・null・未知項目を拒否。入力値・例外contextを応答へ返さない |
| 要求IDと内部情報 | 成功/失敗ともサーバーUUIDを返し、エラー本文とヘッダーが一致。送信された要求IDは不採用。例外メッセージ・Authorization・クエリの値が応答とアプリ要求ログに出ない |
| 実HTTP | CLIを一時ポートで実行し、GET /health=200、GET /missing=404、POST /health=405、要求IDとAllowを確認 |
| 待受・停止 | lsofで127.0.0.1だけの待受を確認。SIGINTによる終了コード0・待受ポートの接続拒否を確認 |
| 契約の回帰 | 更新したYAMLで既存6テストグループ成功。15操作を維持 |
| lint・書式 | apps/apiとscriptsのRuff check成功、format --checkは18ファイル成功 |
| 配布物 | sdistからwheel作成成功。秘密設定・テストを含まず、APIの各モジュールを含むことを確認 |
| ロック再導入 | 空の別venvにruntimeだけをlocked/offline導入しwheelへ入替。リポジトリ外の作業ディレクトリからimport・アプリ生成成功。pytestなしで動作し、ロックSHA-256は前後一致 |
| 文書と公開情報 | 公開Markdown27本・相対リンク145件・シェル69ブロック、表・フェンス・YAML/JSONを確認。実トークン混入なしと個人用2資料・認証ファイルのGit除外を確認 |
| 既存範囲 | Next.js・Node指定・Compose・ローカルAWS検証環境・設計検証スクリプト・架空データ・Day 0〜4記事はday04から不変。変更のないフロントのビルドとMiniStack検証は再実行していない |

最新StarletteのTestClientが旧HTTPX利用を非推奨としていたため、テスト依存をHTTPX2へ合わせてから最終確認した。警告を抑制する設定は追加していない。

## レビュー項目

1. 現段階はhealthと共通基盤までで、商品・売上・認証・保存処理が完成したと扱っていないこと。
2. OS環境優先、dotenv明示指定、モード別のURL拒否と、SDK接続をDay 6へ分ける方針。
3. 404/405・400/422・500の形式、要求ID、内部情報を返さないメッセージとログ。
4. `sales-manager-api`がHTTPサーバーを起動するようになった変更と、127.0.0.1限定・Ctrl+C停止の手順。
5. 契約の正本をYAMLのまま保ち、追加した500と要求ID、将来の未実装操作を区別していること。

## 未実装・未検証

SDKクライアント・DynamoDB保存はDay 6以降、商品/売上APIはDay 7以降。401/409の試験は応答形式だけで、認証や冪等性処理の実装完了を意味しない。CORS・Next.js接続・Lambdaアダプター・AWS配備・性能試験は該当Dayで行う。

応答開始後の例外・ストリーミングと、ASGIアプリへ届く前の不正HTTP構文は今回の検証範囲外。healthは接続準備やデータの正常性を確認するreadinessではない。

記事は2026-12-05公開予定、Qiita URLは未取得。投稿・予約・全体公開の操作は行っていない。PRは既定のブラウザー操作で作成・マージし、実URLは作成後に記録する。Day 5のレビューは未承認、mainマージ・day05タグ・Day 6は未着手。
