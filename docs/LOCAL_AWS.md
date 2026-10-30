# ローカルAWS環境：MiniStackとLocalStackの比較

確認日：2026-10-29（Asia/Tokyo）。Day 3の実装・レビュー対象。業務データの保存処理はDay 6、アプリの認証はDay 19、AWSへのデプロイはDay 22・23で扱う。

## 採用判断

今回は **MiniStack 1.5.33** をローカル開発に採用する構成とした。SDKによるDynamoDB・S3の読み書き、CognitoのログインとJWKSを使ったRS256署名検証、再起動・再作成後の状態保持を実測できたためである。MiniStackはMITライセンスで公開され、今回の起動にアカウントやAuth Tokenは使っていない。[固定版のライセンス](https://github.com/ministackorg/ministack/blob/v1.5.33/LICENSE)

LocalStack 2026.8.2は、最初にAuth Tokenなしで起動して終了コード55となった。その後、Auth Tokenをローカルに設定して再比較し、**認証と起動に成功した**。DynamoDB・S3の読み書きと検証リソースの削除も成功した。一方、CognitoのCreateUserPoolは「cognito-idpが現在のライセンスに含まれていない」というInternalFailureで拒否された。起動失敗だけを採用判断の根拠とせず、無料でCognitoも検証する今回の目的に合わせてMiniStackを推奨する。[LocalStack公式導入手順](https://docs.localstack.cloud/aws/getting-started/installation/)

| 比較項目 | MiniStack 1.5.33 | LocalStack 2026.8.2 |
| --- | --- | --- |
| 起動条件 | アカウント・Auth Tokenなしで起動成功 | Auth Tokenなしは終了コード55。設定後は認証有効・起動成功 |
| DynamoDB・S3 | 架空データの書込・読取・削除が成功 | 同じSDK処理で書込・読取・削除が成功 |
| Cognito | プール・クライアント・ユーザー作成、ログイン、JWKS取得、署名検証が成功 | CreateUserPoolが現在の無料ライセンスの対象外として拒否。ログイン・署名検証は未実施 |
| 不正入力の拒否 | 誤パスワードと改ざんJWTの拒否を確認 | Cognitoが利用できず未検証 |
| 状態保持 | コンテナ再起動と削除・再作成後のデータ・ユーザー・署名鍵を確認 | 永続化構成は未構築・未検証。公式資料ではBase・Ultimateが対象 |
| CPU | 今回はlinux/arm64で実行。配布manifestにはamd64も存在 | 同左。APIの同等性を意味しない |
| AWSへの移行 | 標準AWS SDKを使用。実AWSでは接続設定・資格情報・IaCを別途検証 | 標準AWS SDKとIaC向けの公式案内あり。今回はデプロイ未検証 |

これは今回の利用資格・構成で確認した比較であり、全API互換性や有料プランを含めた製品全体の優劣は判定していない。2026-10-30には、後述の条件で起動時間とアイドル時の使用量も測定した。APIの負荷性能は未測定。LocalStackのCognitoと永続化は、現行公式資料ではBase・Ultimateが対象。別の利用資格では結果が変わり得る。[Cognito資料](https://docs.localstack.cloud/aws/services/cognito-idp/)、[永続化資料](https://docs.localstack.cloud/aws/developer-tools/snapshots/persistence/)

ローカルの情報APIでは `is_license_activated=true` を確認したが、契約プラン名と有効期限は応答に含まれなかった。`edition=pro` を有料契約の証拠として扱わず、期限が無期限とも推測しない。利用資格・期限の詳細は管理画面で確認する。

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

## Auth Tokenを設定したLocalStackの比較

ローカルに `.env.localstack` を作成し、`.env.localstack.example` の項目へ自分のAuth Tokenを設定する。実値はGit・記事・PR・チャットへ載せず、このファイルはGitの除外対象とする。以下はすべてプロジェクトルートで実行する。`config` はトークンを展開して表示しないよう、必ず `--quiet` を付ける。

```sh
git check-ignore .env.localstack
docker compose --env-file .env.localstack -f infra/local-aws/compose.localstack.yaml config --quiet
docker compose --env-file .env.localstack -f infra/local-aws/compose.localstack.yaml up -d --wait --wait-timeout 90
uv run --project infra/local-aws --locked python scripts/verify_local_aws.py --endpoint http://127.0.0.1:4567 --data-only
docker compose --env-file .env.localstack -f infra/local-aws/compose.localstack.yaml down
```

`--data-only` はDynamoDB・S3だけを検証する明示的なモードで、Cognitoは `not_requested` と出力する。Cognitoを含む既定モードを自動的にデータ専用へ切り替えて成功扱いにはしない。今回のデータ専用結果は次のとおり。

```json
{
  "endpoint": "http://127.0.0.1:4567",
  "region": "ap-northeast-1",
  "dynamodb_read_write": "passed",
  "s3_read_write": "passed",
  "cognito_login_jwks_rs256_tamper_wrong_password": "not_requested",
  "fixture_cleanup": "passed"
}
```

Cognitoを含む同じ検証も、LocalStack起動中に実行した。

```sh
uv run --project infra/local-aws --locked python scripts/verify_local_aws.py --endpoint http://127.0.0.1:4567
```

今回の無料ライセンス条件ではCreateUserPoolに対して「cognito-idp service is not included within your LocalStack license」と返り、スクリプトは終了コード1となった。DynamoDB・S3だけの成功をCognitoまで検証済みとは扱わない。別のライセンスで再比較する場合は、有効な利用資格を確認して同じ検証を実行する。有料契約・プラン変更は今回行っていない。

### 最初のトークンなしの条件

以下は今回実行した「Auth Tokenなし」の条件を再現する。ローカルAWSの既定起動には含めない。

```sh
env -u LOCALSTACK_AUTH_TOKEN docker compose --env-file /dev/null -f infra/local-aws/compose.localstack.yaml up -d
docker compose --env-file /dev/null -f infra/local-aws/compose.localstack.yaml ps -a
docker compose --env-file /dev/null -f infra/local-aws/compose.localstack.yaml logs --tail 30
docker compose --env-file /dev/null -f infra/local-aws/compose.localstack.yaml down
```

この最初の条件では `No credentials were found in the environment` により終了コード55となった。上記の再比較で、Auth Tokenの設定により起動できることを確認した。

## 起動時間とアイドル負荷の追加測定

測定日：2026-10-30（Asia/Tokyo）。[匿名化した全6試行と中央値](benchmarks/day03-local-aws-20261030.json) を保存した。再現用コードは `scripts/benchmark_local_aws.py`。

同じDocker環境のlinux/arm64イメージを使用し、DynamoDB・S3だけを有効にした。各コンテナの上限はCPU 2コア・メモリ1GiB。各製品3試行を直列に実行し、順番はMiniStack→LocalStack→LocalStack→MiniStack→MiniStack→LocalStackとした。毎回新しいコンテナと空のデータを使い、既存のComposeボリュームには接続していない。

| 指標（3試行の中央値） | MiniStack 1.5.33 | LocalStack 2026.8.2 |
| --- | --- | --- |
| HTTP 200まで | 0.692秒 | 7.386秒 |
| DynamoDB・S3のAPI成功まで | 1.065秒 | 8.607秒 |
| API初回呼出し後のアイドルメモリ | 51.56MiB | 405.3MiB |
| 同時点のCPU使用率 | 0.00% | 0.07% |
| イメージのDocker報告値（`.Size`） | 64.8MiB | 429.1MiB |

起動時間は `docker start` の直前から測り、HTTPは外部から0.1秒間隔で確認する。API成功までの時間はLocalStackの認証有効化と、両者のListTables・ListBucketsの成功までを含む。イメージ取得・コンテナ作成は計測外。Composeのhealthcheck間隔の違いを避けるため、測定用コンテナでは内蔵healthcheckを無効にした。

メモリ・CPUはAPI成功の5秒後から `docker stats --no-stream` で3回取得し、その中央値を試行の代表値とした。表はさらに3試行の中央値である。メモリはLinuxのDocker CLIがキャッシュを控除した値で、Mac全体の使用量ではない。CPUの0.00%は表示精度と短い採取期間による値で、常にCPUを使わないという意味ではない。[Docker statsの定義](https://docs.docker.com/reference/cli/docker/container/stats/)

今回の条件では、MiniStackのAPI準備時間とアイドルメモリはLocalStackの約1/8だった。LocalStackのライセンス認証にかかる通信、キャッシュ、ホストの負荷でも変わるため、全環境・全バージョンに一般化しない。永続化を両者とも無効にし、Cognito・Lambda・業務データ・負荷試験は含めていない。`.Size` はDocker APIの報告値であり、取得時間や重複排除後のディスク消費量ではない。

`.env.localstack` と検証専用の依存を準備した後、プロジェクトルートで再測定できる。毎回6個の測定用コンテナを順に作成・削除する。LocalStackの利用資格は実行時点で有効なものが必要。

```sh
uv run --project infra/local-aws --locked python scripts/benchmark_local_aws.py --output .cache/day03-benchmark.json
```

## 軽量性以外の利点

- エミュレーター利用のアカウント登録やAuth Tokenを用意せずに起動できる。読者の環境構築や、将来のCIでLocalStack用トークンを配布・管理する作業を省ける。CI自体の導入・検証はDay 21で行う。
- MiniStack 1.5.33はMITライセンスでソースを公開している。採用版の内部実装を参照して、挙動や制限を調べられる。[固定版のライセンス](https://github.com/ministackorg/ministack/blob/v1.5.33/LICENSE)
- 今回の構成では、Cognitoの基本操作と通常停止時の状態保持を無料で検証できた。対応APIが増えても実AWSとの差は各Dayで確認する。

公式にも起動・メモリの小ささやアカウント不要という説明があるが、上の表には提供元の宣伝値ではなく今回の実測値を使った。[MiniStack公式](https://ministack.org/)

## AWSへのデプロイに向けて残す境界

エミュレーターをAWSに変換してデプロイするのではなく、アプリとIaCの接続設定を環境ごとに分ける。ローカル用URL・ダミー資格情報・ローカルJWKSはAWS環境へ持ち込まない。AWSではIAMロールと実サービスのissuer・公開鍵を使う設計を後続Dayで検証する。

今回未検証なのは、DynamoDBトランザクション・条件式・索引・ページング、S3の署名付きURL・CORS、Cognitoのブラウザー認証・PKCE・MFA・SRP・失効・ロール、API Gateway/Lambda、IaC、AWS実環境のIAM・通信・課金条件。MiniStackの既知の差分も後続Dayで確認し、必要な実AWSでの確認を残す。[MiniStackの既知の制限](https://ministack.org/docs/limitations)

検証結果とレビュー項目は [DAY3_REVIEW.md](DAY3_REVIEW.md) に記録する。
