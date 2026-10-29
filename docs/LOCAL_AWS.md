# ローカルAWS環境：MiniStackとLocalStackの比較

確認日：2026-10-29（Asia/Tokyo）。Day 3の実装・レビュー対象。業務データの保存処理はDay 6、アプリの認証はDay 19、AWSへのデプロイはDay 22・23で扱う。

## 採用判断

今回は **MiniStack 1.5.33** をローカル開発に採用する構成とした。SDKによるDynamoDB・S3の読み書き、CognitoのログインとJWKSを使ったRS256署名検証、再起動・再作成後の状態保持を実測できたためである。MiniStackはMITライセンスで公開され、今回の起動にアカウントやAuth Tokenは使っていない。[固定版のライセンス](https://github.com/ministackorg/ministack/blob/v1.5.33/LICENSE)

LocalStack 2026.8.2も実際に起動したが、Auth Tokenを渡さない条件ではライセンス認証に失敗し、終了コード55で停止した。現行の公式導入手順にもAuth Tokenが必要と記載されている。[LocalStack公式導入手順](https://docs.localstack.cloud/aws/getting-started/installation/)

| 比較項目 | MiniStack 1.5.33 | LocalStack 2026.8.2 |
| --- | --- | --- |
| 起動条件 | アカウント・Auth Tokenなしで起動成功 | 今回はAuth Tokenなしで起動失敗。有効な利用資格・トークンでの起動は未検証 |
| DynamoDB・S3 | 架空データの書込・読取・削除が成功 | 起動失敗のためAPI動作は未検証 |
| Cognito | プール・クライアント・ユーザー作成、ログイン、JWKS取得、署名検証が成功 | 起動失敗のためAPI動作は未検証。公式資料には対応APIが掲載されている |
| 不正入力の拒否 | 誤パスワードと改ざんJWTの拒否を確認 | 未検証 |
| 状態保持 | コンテナ再起動と削除・再作成後のデータ・ユーザー・署名鍵を確認 | 未検証 |
| CPU | 今回はlinux/arm64で実行。配布manifestにはamd64も存在 | 同左。APIの同等性を意味しない |
| AWSへの移行 | 標準AWS SDKを使用。実AWSでは接続設定・資格情報・IaCを別途検証 | 標準AWS SDKとIaC向けの公式案内あり。今回はデプロイ未検証 |

これは利用条件と今回動かせた範囲の比較であり、同条件での性能測定や全API互換性の比較ではない。LocalStackでCognitoが一律に利用できないという結論ではない。利用可能プランとAPI範囲は採用時点で確認する。[LocalStackのCognito資料](https://docs.localstack.cloud/aws/services/cognito-idp/)

## 固定した環境

検証ホストはmacOS・Apple Silicon。Docker Engine / CLI 29.1.2、Compose v2.40.3-desktop.1。PythonはDay 2と同じ3.14.9、uvは0.13.6を使用する。

- `compose.yaml`：MiniStack `1.5.33`、multi-platform index digest `sha256:b58186186515a372798ccf0ca9975c295db219b5a811975337d6967b968e07b4`。
- `infra/local-aws/compose.localstack.yaml`：比較用LocalStack `2026.8.2`、index digest `sha256:3fe5b51caec82b966a34485b5b43efd68075ff8161f9b0a34091fad9abb0ff82`。
- `infra/local-aws/pyproject.toml` と `uv.lock`：検証専用のBoto3 1.43.121、PyJWT 2.15.1、cryptography 50.0.2と間接依存を固定。

アプリ本体の `apps/api/` と `apps/web/` の依存・ロックファイルは変更しない。検証専用の仮想環境は `infra/local-aws/.venv/` に作成する。

## 起動と接続確認

[Day 2の手順](DEVELOPMENT.md) に従い、Python・uvを準備する。以下はすべてプロジェクトルートで実行する。Docker Desktop等のDocker Engineを起動しておく。

```sh
docker version
docker compose version
uv sync --project infra/local-aws --locked
docker compose --env-file /dev/null -f compose.yaml config --quiet
docker compose --env-file /dev/null -f compose.yaml up -d --wait --wait-timeout 90
docker compose --env-file /dev/null -f compose.yaml ps
curl --noproxy '*' --fail --silent --output /dev/null --write-out 'HTTP %{http_code}\n' http://127.0.0.1:4566/_ministack/health
uv run --project infra/local-aws --locked python scripts/verify_local_aws.py
```

`--env-file /dev/null` はComposeによるローカル `.env` の自動読込を避ける指定。MiniStackには本物のAWS資格情報もAuth Tokenも不要。ヘルスチェックはHTTP 200を返すが、API機能を保証するものではないため、続けてSDKの検証を行う。

検証スクリプトは `day03-probe-` で始まる一意のテーブル・バケット・プールを作り、架空の値だけを書き込む。パスワードとJWTは表示しない。正常終了時に検証リソースを削除する。既存の業務データは使用しない。

## 接続先と資格情報の分離

| 項目 | Day 3の検証設定 |
| --- | --- |
| ホストからの接続先 | `http://127.0.0.1:4566` |
| 比較用LocalStack | `http://127.0.0.1:4567` |
| リージョン | `ap-northeast-1` |
| AWSアクセスキー / シークレット | 検証用プロセスで `test` / `test` を明示 |
| 公開するポート | ホストの `127.0.0.1` に限定 |
| コンテナ内のヘルスチェック | コンテナ自身の `127.0.0.1:4566` |

`scripts/verify_local_aws.py` はURLを許可リストで検査し、省略・外部ホスト・パス・クエリ・ユーザー情報付きURLなどをSDKクライアントの作成前に拒否する。接続失敗時に実AWSへ切り替えない。SDKにはendpoint、リージョン、ダミー資格情報、S3のpath形式を明示し、HTTPプロキシを使わない。検証プロセス内では個人用AWSプロファイル・設定ファイル・メタデータ認証も使わない。[Boto3の設定資料](https://docs.aws.amazon.com/boto3/latest/guide/configuration.html)

CognitoのJWTにAWS形式のissuerが入っていても、そのURLへ公開鍵を取得しに行かない。検証スクリプトは同じローカル接続先のJWKSを取得し、署名・有効期限・issuer・token_use・アプリクライアントを検証する。ホストのhostsファイルや証明書ストアを変更しない。[AWSのJWT検証資料](https://docs.aws.amazon.com/cognito/latest/developerguide/amazon-cognito-user-pools-using-tokens-verifying-a-jwt.html)

これらはDay 3の検証ツールの境界である。アプリAPIの設定読込・ローカル/AWS切替の拒否条件はDay 5で実装・テストする。Docker内の別サービスから接続する場合はサービス名を使う設定が必要となり、今回のホスト用許可リストをそのまま流用しない。

## 停止・再起動・データ保持

```sh
docker compose --env-file /dev/null -f compose.yaml stop
docker compose --env-file /dev/null -f compose.yaml up -d --wait --wait-timeout 90
uv run --project infra/local-aws --locked python scripts/verify_local_aws.py --lifecycle
docker compose --env-file /dev/null -f compose.yaml down
```

`--lifecycle` は専用コンテナを実際に再起動し、さらに `down` → `up` で再作成する。起動中の本プロジェクトのローカル接続は一時的に切れる。検証用データの一致、Cognitoユーザーの参照、再作成前のJWTを同じ公開鍵で検証できることまで確認し、最後に検証リソースを削除する。対象は既定のMiniStackだけで、比較用URLを指定したライフサイクル操作は拒否する。

Composeの名前付きボリューム `sales-manager-dashboard-local_aws-local-data` に状態とS3の内容を保持する。`PERSIST_STATE=1`、`STATE_DIR`、`S3_PERSIST=1`、`S3_DATA_DIR` を明示し、通常の停止時に保存させるため30秒の停止猶予を設けた。通常の `down` では名前付きボリュームを残す。強制終了・障害時の耐久性やバックアップの代わりにはならない。[MiniStackの設定資料](https://ministack.org/docs/configuration)、[Composeの削除対象](https://docs.docker.com/reference/cli/docker/compose/down/)

ローカルデータをすべて破棄して初期化する場合だけ、次を実行する。本プロジェクトの名前付きボリューム内のデータとローカル署名鍵を削除する。

```sh
docker compose --env-file /dev/null -f compose.yaml down --volumes
```

取得したDockerイメージとDocker Desktop自体は通常の `down` では削除・終了しない。プロジェクト外のPython・Node.js・シェル設定・AWS設定ファイルには変更を加えない。

## LocalStackを再比較する場合

以下は今回実行した「Auth Tokenなし」の条件を再現する。ローカルAWSの既定起動には含めない。

```sh
env -u LOCALSTACK_AUTH_TOKEN docker compose --env-file /dev/null -f infra/local-aws/compose.localstack.yaml up -d
docker compose --env-file /dev/null -f infra/local-aws/compose.localstack.yaml ps -a
docker compose --env-file /dev/null -f infra/local-aws/compose.localstack.yaml logs --tail 30
docker compose --env-file /dev/null -f infra/local-aws/compose.localstack.yaml down
```

今回の結果は `No credentials were found in the environment` による終了コード55。トークンを利用する再比較は、利用資格を確認してから環境変数で渡し、実値をファイル・記事・PRへ貼らない。起動できた場合は同じ検証を `--endpoint http://127.0.0.1:4567` で行えるが、今回は未実施。

## AWSへのデプロイに向けて残す境界

エミュレーターをAWSに変換してデプロイするのではなく、アプリとIaCの接続設定を環境ごとに分ける。ローカル用URL・ダミー資格情報・ローカルJWKSはAWS環境へ持ち込まない。AWSではIAMロールと実サービスのissuer・公開鍵を使う設計を後続Dayで検証する。

今回未検証なのは、DynamoDBトランザクション・条件式・索引・ページング、S3の署名付きURL・CORS、Cognitoのブラウザー認証・PKCE・MFA・SRP・失効・ロール、API Gateway/Lambda、IaC、AWS実環境のIAM・通信・課金条件。MiniStackの既知の差分も後続Dayで確認し、必要な実AWSでの確認を残す。[MiniStackの既知の制限](https://ministack.org/docs/limitations)

検証結果とレビュー項目は [DAY3_REVIEW.md](DAY3_REVIEW.md) に記録する。
