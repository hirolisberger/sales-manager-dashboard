# Day 3：ローカルAWS環境の比較と検証

確認日：2026-10-29（Asia/Tokyo）。`feature/day03`、基点main / `day02`：`b302057066db9cf8ad9cd61d638b2ac071e2d448`。

実装・記事・必要なローカル検証は完了し、**2026-10-30にユーザーレビュー承認済み**。[PR #2](https://github.com/hirolisberger/sales-manager-dashboard/pull/2) はブラウザーでマージ済み。マージコミットと [day03タグ](https://github.com/hirolisberger/sales-manager-dashboard/tree/day03) は `9cb473ddf23673b3d474537e18ce259f05547c7e` を参照する。feature/day03は保持。Day 4はその後のユーザー開始指示で着手した。

## 今回の成果物

- `compose.yaml`：MiniStack 1.5.33をdigest固定で起動。loopback公開、ヘルスチェック、名前付きボリューム、停止猶予。
- `infra/local-aws/compose.localstack.yaml`：LocalStack 2026.8.2の独立した比較用構成。既定起動には含めない。
- `.env.localstack.example`：Auth Tokenの設定項目だけを共有する見本。実値を置く `.env.localstack` はGit対象外。
- `infra/local-aws/pyproject.toml`・`uv.lock`・`.python-version`：検証専用SDK・JWT依存とPythonを固定。アプリ本体の依存は変更しない。
- `scripts/verify_local_aws.py`：架空データのSDK検証、Cognito/JWKS/RS256検証、任意の再起動・再作成確認と検証リソースの削除。再比較でデータ専用の `--data-only` を追加し、省略したCognitoは `not_requested` と記録。
- `scripts/test_local_aws.py`：外部URL拒否、既存AWSプロファイル・資格情報・プロキシの分離を確認。
- `scripts/benchmark_local_aws.py` と [全6試行の測定値](benchmarks/day03-local-aws-20261030.json)：独立したコンテナでの起動・アイドル負荷比較。
- [手順と比較](LOCAL_AWS.md)、[記事](../qiita/day03-ministack-localstack-local-aws.md)、README・計画・開発ルールの更新。

MiniStackを採用する構成をレビュー対象とする。レビュー中の再比較依頼に対応し、LocalStackでもAuth Token設定後の起動とDynamoDB・S3の同じSDK検証に成功した。Cognitoは現在の無料ライセンス対象外としてCreateUserPoolを拒否した。無料でCognitoも含めて検証する目的に対してMiniStackを推奨する。2026-10-30にはDynamoDB・S3限定で起動とアイドル負荷を追加測定した。API負荷性能・別ライセンス・AWSへのデプロイは未検証。条件と固定イメージは手順書に記録する。

## 実施した確認

環境：macOS ARM64、Docker 29.1.2、Compose v2.40.3-desktop.1、Python 3.14.9、uv 0.13.6。

| 確認 | 実行方法・結果 |
| --- | --- |
| 前Dayの完了 | PR #1がマージ済み、mainとday02がb302057を参照。最新originをfetch後にfeature/day03を作成 |
| イメージ固定 | 両イメージのindex digestとamd64/arm64配布を確認し、arm64を取得 |
| Composeの構文 | 両構成の `docker compose ... config --quiet` が成功 |
| MiniStack起動 | `docker compose --env-file /dev/null -f compose.yaml up -d --wait --wait-timeout 90` がhealthyで成功 |
| LocalStack起動 | Auth Tokenを除いた環境で起動。ライセンス認証失敗で終了コード55。起動失敗を採用条件の比較結果として記録 |
| LocalStack再比較：認証 | Git対象外のローカル設定からAuth Tokenを渡し、起動成功。情報APIで `is_license_activated=true` を確認。プラン名・有効期限はAPI応答から特定できない |
| LocalStack再比較：DynamoDB/S3 | 同じ検証の `--endpoint http://127.0.0.1:4567 --data-only` が終了コード0。書込・読取・検証リソース削除が成功。Cognitoは `not_requested` と区別 |
| LocalStack再比較：Cognito | Cognitoを含む既定モードも実行。CreateUserPoolにInternalFailure・現在のライセンスにcognito-idpが含まれない旨が返り、終了コード1。認証失敗とは区別して記録 |
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
| 文書と公開情報 | 認証付き再比較時はMarkdown 18本・相対リンク77件・シェル44ブロック。起動測定の追記後は18本・79件・46ブロックの構文、表・フェンス、記事YAMLとComposeの完全一致を確認した。公開対象への実トークン混入なし、匿名化・実設定ファイルのGit除外も確認した |
| 接続範囲・終了状態 | HTTP 200・バージョン1.5.33・127.0.0.1公開・Dockerソケット非マウントを確認。再比較したLocalStackもComposeのhealthyを確認し、両構成をdown。4566・4567番への接続拒否を確認。MiniStackの名前付きボリュームは保持 |

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

1. Auth Token設定後のLocalStackでもDynamoDB・S3は動作した一方、Cognitoは無料ライセンス対象外だったことを踏まえ、MiniStackを採用する判断。
2. `LOCAL_AWS.md` の手順で起動・接続確認・停止できること。`--lifecycle` は本プロジェクトのコンテナを再起動・再作成する。
3. 個人用AWS資格情報を使わず、ホストのhosts・証明書ストアを変更しない構成。
4. 通常のdownではボリュームを残し、明示的な `down --volumes` でローカルデータを破棄する方針。
5. Cognitoの確認は検証専用であり、アプリへのログイン機能追加はDay 19とすること。AWSへの移行容易性はまだ実証していないこと。
6. 記事の冒頭・独立した結論節・まとめに「MiniStack 1.5.33を採用し、Day 4以降も使う」と明記し、その理由が今回の利用条件・実測結果に合っていること。過去の承認済み記事は書き換えない。

## 2026-10-30：記事の採用結論を明確化

レビュー指摘を受け、冒頭とまとめの採用方針を強調し、「結論：このプロジェクトではMiniStackを採用する」の節を追加した。無料でCognitoと状態保持まで確認できたことを理由とし、Day 4以降もMiniStackを標準にする方針を明記する。これは記事で説明する技術選定であり、ユーザーのレビュー承認や次のDayの開始を完了したとは扱わない。

この結論明確化の修正では、記事の説明とレビュー記録のみ変更した。実装・Compose・依存関係・記事内コードブロック・検証結果は2026-10-29の提出内容から変更せず、文書差分・書式・リンクを確認した。当該修正では実行環境の再検証を行わなかった。起動・アイドル負荷の追加測定は次節に分けて記録する。

## 2026-10-30：起動・アイドル負荷と追加の利点を確認

`uv run --project infra/local-aws --locked python scripts/benchmark_local_aws.py --output .cache/day03-benchmark-20261030.json` を実行し、両製品を各3回測定した。DynamoDB・S3、CPU 2コア・メモリ1GiB、空の新規コンテナ、永続化無効、外部HTTPポーリング、キャッシュ済みイメージという共通条件にそろえた。既存のComposeデータ・設定は変更していない。

中央値は、HTTP 200までMiniStack 0.692秒 / LocalStack 7.386秒、API成功まで1.065秒 / 8.607秒、アイドルメモリ51.56MiB / 405.3MiB、CPU 0.00% / 0.07%。全6試行の値と集計を照合し、測定用コンテナがすべて削除されたことを確認した。新しい測定スクリプトのRuffも成功。

公式の軽量性の説明と今回の実測値を分け、記事と手順書へ条件・制限を追記した。アカウント・Auth Tokenが不要な導入と、固定版のMITライセンスによるソース公開も利点として整理する。API負荷時の性能、Cognito・Lambda利用時の使用量、他環境での再現、CIは今回未検証。既存の機能検証を再実行したとは扱わない。

## ユーザーレビュー承認

| 項目 | 結果 |
| --- | --- |
| レビュー | 承認済み（2026-10-30・Asia/Tokyo） |
| 承認対象 | `50a5b1d6469669e505296022b6c78b1bc08110eb` |
| 承認範囲 | MiniStack採用、ローカル環境・検証、追加測定と記事の提出内容 |
| 承認後の変更 | 承認・次回条件の記録のみ。実装・設定・記事内コード・測定データは変更しない |
| PR・マージ・タグ | 未完了。PRをブラウザーで作成し、Create a merge commitでマージ後、そのコミットへday03タグを付ける |

## 未検証・残件とレビュー状態

- LocalStackのAuth Token設定後の起動・DynamoDB・S3・Cognitoのライセンス拒否は確認済み。Cognitoのログイン以降、永続化構成、別のライセンス条件、API負荷性能は未検証。起動・アイドル負荷は上記の条件だけで比較済み。有効期限は未特定。
- 他OS・amd64実行、ブラウザー認証・MFA等、DynamoDBトランザクション等の業務要件、IaC・AWSへのデプロイは今回の対象外。[手順書の未検証一覧](LOCAL_AWS.md) を参照する。
- アプリのHTTP API・ローカル/AWS設定の読込は未実装。今回の検証ツールにだけ接続先の拒否条件を実装した。
- `day03` タグは承認・PRマージ後に作成するため、記事のタグURLはまだ有効性を確認していない。
- レビュー承認は完了。PR作成・mainマージ・タグ作成・Qiita投稿は未実施。公開予定日は2026-12-03（日本時間）を維持する。Day 4はPRマージとユーザーの開始指示を待つ。

## 2026-10-30：マージ・タグの補完記録

PR #2のマージ日時は2026-10-30T10:45:37+09:00。mainと注釈付きday03タグの一致を確認した。Day 4ブランチでこの完了記録のみ補完し、Day 3の実装・測定値・記事本文は変更していない。
