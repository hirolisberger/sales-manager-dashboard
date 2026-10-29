# Day 3：ローカルAWS環境の比較と検証

確認日：2026-10-29（Asia/Tokyo）。`feature/day03`、基点main / `day02`：`b302057066db9cf8ad9cd61d638b2ac071e2d448`。

実装・記事・必要なローカル検証は完了し、**ユーザーレビュー待ち**。PRは前回と同様にブラウザーで作成する手順を用意する。作成済みPRのURLはまだ未取得。承認前にmainへマージせず、Day 4を開始しない。

## 今回の成果物

- `compose.yaml`：MiniStack 1.5.33をdigest固定で起動。loopback公開、ヘルスチェック、名前付きボリューム、停止猶予。
- `infra/local-aws/compose.localstack.yaml`：LocalStack 2026.8.2の独立した比較用構成。既定起動には含めない。
- `infra/local-aws/pyproject.toml`・`uv.lock`・`.python-version`：検証専用SDK・JWT依存とPythonを固定。アプリ本体の依存は変更しない。
- `scripts/verify_local_aws.py`：架空データのSDK検証、Cognito/JWKS/RS256検証、任意の再起動・再作成確認と検証リソースの削除。
- `scripts/test_local_aws.py`：外部URL拒否、既存AWSプロファイル・資格情報・プロキシの分離を確認。
- [手順と比較](LOCAL_AWS.md)、[記事](../qiita/day03-ministack-localstack-local-aws.md)、README・計画・開発ルールの更新。

MiniStackを採用する構成をレビュー対象とする。LocalStackはAuth Tokenなしでライセンス認証に失敗して終了したため、同一APIを実行しての優劣・性能比較は行えていない。条件と固定イメージは手順書に記録する。

## 実施した確認

環境：macOS ARM64、Docker 29.1.2、Compose v2.40.3-desktop.1、Python 3.14.9、uv 0.13.6。

| 確認 | 実行方法・結果 |
| --- | --- |
| 前Dayの完了 | PR #1がマージ済み、mainとday02がb302057を参照。最新originをfetch後にfeature/day03を作成 |
| イメージ固定 | 両イメージのindex digestとamd64/arm64配布を確認し、arm64を取得 |
| Composeの構文 | 両構成の `docker compose ... config --quiet` が成功 |
| MiniStack起動 | `docker compose --env-file /dev/null -f compose.yaml up -d --wait --wait-timeout 90` がhealthyで成功 |
| LocalStack起動 | Auth Tokenを除いた環境で起動。ライセンス認証失敗で終了コード55。起動失敗を採用条件の比較結果として記録 |
| SDKとCognito | `uv run --project infra/local-aws --locked python scripts/verify_local_aws.py --lifecycle` が終了コード0 |
| DynamoDB | 一意名のテーブル作成、架空の1,430円の書込・強い整合性での読取・削除が成功 |
| S3 | 一意名のバケット・架空オブジェクト作成、内容一致・削除が成功 |
| Cognito | プール・クライアント・ユーザー作成、USER_PASSWORD_AUTH、ローカルJWKSによるID/access tokenのRS256署名とclaimsの検証が成功 |
| 拒否の確認 | 誤パスワードはNotAuthorizedException、元のID tokenと同じ公開鍵で改ざんJWTの署名不一致を確認 |
| 再起動・再作成 | restart後と、ボリュームを残すdown/up後にデータ・ユーザーを参照でき、以前のJWTを同じ公開鍵で検証できた |
| 後片付け | スクリプトが作成したテーブル・バケット・プールの削除が成功 |
| 接続境界の単体確認 | `uv run --project infra/local-aws --locked python -m unittest discover -s scripts -p 'test_*.py' -v`：4件成功 |
| ロックからの再導入 | 別の空の仮想環境へ `uv sync --locked --offline` で導入し、SDK・JWT・暗号ライブラリをimport。ロックのSHA-256は再導入前後で一致 |
| 静的検証・書式 | `uv run --project apps/api --locked ruff check --config infra/local-aws/pyproject.toml scripts` と同設定の `ruff format --check` が成功 |
| アプリへの影響 | `git diff --exit-code day02 -- apps .nvmrc` が成功。アプリのコード・依存・ロックはDay 2から変更なし |
| 文書と公開情報 | Markdown 18本、相対リンク76件、シェルブロック39件の構文、表・フェンス、記事YAMLとComposeの完全一致、匿名化・Git除外を確認 |
| 接続範囲・終了状態 | HTTP 200・バージョン1.5.33・127.0.0.1公開・Dockerソケット非マウントを確認。両Compose構成をdownし、4566番への接続拒否を確認。名前付きボリュームは保持 |

スクリプトの最終結果は次のとおり。JWT、パスワード、個人用の資格情報は含めない。

```json
{
  "endpoint": "http://127.0.0.1:4566",
  "region": "ap-northeast-1",
  "dynamodb_read_write": "passed",
  "s3_read_write": "passed",
  "cognito_login_jwks_rs256_tamper_wrong_password": "passed",
  "restart_data_user_signing_key": "passed",
  "recreate_data_user_signing_key": "passed",
  "fixture_cleanup": "passed"
}
```

## レビューで確認してほしいこと

1. Auth Tokenを用意せず動作確認できたMiniStackを採用する判断と、LocalStackのAPI比較は未実施とする線引き。
2. `LOCAL_AWS.md` の手順で起動・接続確認・停止できること。`--lifecycle` は本プロジェクトのコンテナを再起動・再作成する。
3. 個人用AWS資格情報を使わず、ホストのhosts・証明書ストアを変更しない構成。
4. 通常のdownではボリュームを残し、明示的な `down --volumes` でローカルデータを破棄する方針。
5. Cognitoの確認は検証専用であり、アプリへのログイン機能追加はDay 19とすること。AWSへの移行容易性はまだ実証していないこと。
6. 記事タイトルと説明が、MiniStack・LocalStackの実測結果に合っていること。過去の承認済み記事は書き換えない。

## 未検証・残件とレビュー状態

- LocalStackの有効な利用資格・Auth Tokenでの起動とAPI検証、両製品の性能比較は未実施。
- 他OS・amd64実行、ブラウザー認証・MFA等、DynamoDBトランザクション等の業務要件、IaC・AWSへのデプロイは今回の対象外。[手順書の未検証一覧](LOCAL_AWS.md) を参照する。
- アプリのHTTP API・ローカル/AWS設定の読込は未実装。今回の検証ツールにだけ接続先の拒否条件を実装した。
- `day03` タグは承認・PRマージ後に作成するため、記事のタグURLはまだ有効性を確認していない。
- レビュー承認、mainへのマージ、タグ作成、Qiita投稿は未実施。公開予定日は2026-12-03（日本時間）を維持する。Day 4には進まない。
