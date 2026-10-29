# 【Day 03】MiniStackとLocalStackを比べてローカルAWS環境を作る

シリーズ：**Next.js・Python・AWSで作る売上管理システム**

公開予定：2026年12月3日（日本時間）。開発・レビューとQiitaへの公開は別に管理しています。

## はじめに

[Day 2](https://github.com/hirolisberger/sales-manager-dashboard/blob/day02/qiita/day02-nextjs-python-development-environment.md)では、Next.jsとPythonを同じリポジトリで起動できるようにしました。今回は、そのPythonから接続するローカルAWS環境を用意します。

当初はLocalStackを使う計画でしたが、Cognitoも含めてローカルで検証したいため、MiniStackと比較することにしました。今回の結果から、以後のローカル開発にはMiniStack 1.5.33を使う構成にしています。以前の記事は企画時のLocalStackを含むシリーズ表記のまま残し、この回から採用した構成を説明します。

リポジトリは [sales-manager-dashboard](https://github.com/hirolisberger/sales-manager-dashboard) です。この回の完成版は [`day03`タグ](https://github.com/hirolisberger/sales-manager-dashboard/tree/day03) で共有する予定です。タグはレビュー承認とmainへのマージ後に作成するため、記事公開前にリンクを確認します。

## この記事の到達点

- MiniStackとLocalStackの起動条件を確認する
- Docker ComposeでローカルAWS環境を起動・停止する
- PythonからDynamoDB・S3・Cognitoの基本APIへ接続する
- 再起動・再作成後の状態保持と、実AWSへ接続しない境界を確認する

公式資料と配布情報の確認日は2026年10月29日です。検証環境はmacOS・Apple Silicon、Docker 29.1.2、Compose v2.40.3-desktop.1、Python 3.14.9、uv 0.13.6です。売上APIとログイン画面の実装は後続Dayで行います。

## 1. どちらを採用するか、起動して確かめる

MiniStackはMITライセンスで公開されているAWSエミュレーターです。今回、アカウント登録やAuth Tokenを使わずに起動できました。[MiniStack 1.5.33のライセンス](https://github.com/ministackorg/ministack/blob/v1.5.33/LICENSE)

LocalStackは2026.8.2を取得しました。Auth Tokenを渡さずに起動したところ、ライセンス認証で停止しました。

```text
LocalStack version: 2026.8.2
License activation failed!
Reason: No credentials were found in the environment.
```

コンテナの終了コードは55でした。現行の公式導入手順も、AWSエミュレーターの有効化にAuth Tokenを必要としています。[LocalStackの公式導入手順](https://docs.localstack.cloud/aws/getting-started/installation/)

| 確認 | MiniStack 1.5.33 | LocalStack 2026.8.2 |
| --- | --- | --- |
| Auth Tokenなしでの起動 | 成功 | ライセンス認証で停止 |
| DynamoDB・S3の読み書き | 成功 | 未検証 |
| Cognitoログイン・JWKS・RS256署名検証 | 成功 | 未検証 |
| 再起動・再作成後の状態保持 | 成功 | 未検証 |

今回は、必要な基本操作を実際に確認できたMiniStackを選びました。この表は同条件でのAPI互換性や性能の比較ではありません。LocalStackのCognitoが利用できないという意味でもなく、有効な利用資格・Auth Tokenでの検証はしていません。[LocalStackのCognito対応資料](https://docs.localstack.cloud/aws/services/cognito-idp/)

## 2. Composeでイメージと保存先を固定する

ルートの `compose.yaml` に、MiniStackのバージョンとイメージのdigestを固定しました。可変の `latest` で起動せず、今回確認したmulti-platformイメージを使います。

```yaml
name: sales-manager-dashboard-local

services:
  aws-local:
    image: ministackorg/ministack:1.5.33@sha256:b58186186515a372798ccf0ca9975c295db219b5a811975337d6967b968e07b4
    ports:
      - "127.0.0.1:4566:4566"
    environment:
      MINISTACK_REGION: ap-northeast-1
      LOG_LEVEL: WARNING
      PERSIST_STATE: "1"
      STATE_DIR: /tmp/ministack-data/state
      S3_PERSIST: "1"
      S3_DATA_DIR: /tmp/ministack-data/s3
    volumes:
      - aws-local-data:/tmp/ministack-data
    healthcheck:
      test:
        - CMD
        - python
        - -c
        - "import urllib.request; urllib.request.urlopen('http://127.0.0.1:4566/_ministack/health', timeout=2)"
      interval: 3s
      timeout: 3s
      start_period: 5s
      retries: 20
    stop_grace_period: 30s

volumes:
  aws-local-data:
```

ホストへ公開するポートは `127.0.0.1` に限定します。Dockerソケットはマウントしていません。今回使うAPIはエミュレーター内で処理できる範囲です。

`PERSIST_STATE` と `S3_PERSIST` は別の設定なので、両方を指定しました。保存先を名前付きボリュームへそろえ、通常の停止時に状態を保存できるようにします。[MiniStackの設定資料](https://ministack.org/docs/configuration)

## 3. 起動とAPIの動作を別々に確認する

以下はすべてリポジトリのルートで実行します。Day 2で用意したPython・uvと、起動済みのDocker Engineが必要です。

```sh
uv sync --project infra/local-aws --locked
docker compose --env-file /dev/null -f compose.yaml config --quiet
docker compose --env-file /dev/null -f compose.yaml up -d --wait --wait-timeout 90
docker compose --env-file /dev/null -f compose.yaml ps
curl --noproxy '*' --fail --silent --output /dev/null --write-out 'HTTP %{http_code}\n' http://127.0.0.1:4566/_ministack/health
```

ヘルスチェックの期待値は `HTTP 200`、Composeの表示はhealthyです。`--env-file /dev/null` で、作業者の `.env` をComposeが自動読込しないようにしています。

起動成功だけではAPIの動作は分からないため、次の検証を実行します。

```sh
uv run --project infra/local-aws --locked python scripts/verify_local_aws.py
```

検証専用の依存は `infra/local-aws/` で管理しました。Boto3 1.43.121、PyJWT 2.15.1、cryptography 50.0.2と間接依存をロックし、仮想環境も同じディレクトリ内に作ります。アプリ本体の依存はDay 2から変更していません。

スクリプトは毎回一意の名前でテーブル・バケット・ユーザープールを作成します。DynamoDBには架空の1,430円、S3には検証用の文字列を保存して読み戻し、最後に検証リソースを削除します。商品・売上の本番用テーブルはまだ作りません。

## 4. Cognitoはログインと署名検証まで試す

Cognitoについては、次の流れを確認しました。

1. ユーザープールとアプリクライアントを作成する
2. 検証ユーザーを登録し、ローカル専用のパスワードを設定する
3. `USER_PASSWORD_AUTH` でログインする
4. ローカルのJWKSから公開鍵を取得し、ID tokenとaccess tokenのRS256署名を検証する
5. 有効期限、issuer、token_use、クライアントIDも確認する
6. 誤パスワードと、内容を改ざんしたJWTを拒否できることを確かめる

JWTをデコードして読めるだけでは署名検証になりません。ID tokenではaud、access tokenではclient_idを確認し、用途をtoken_useで区別します。[AWSのJWT検証資料](https://docs.aws.amazon.com/cognito/latest/developerguide/amazon-cognito-user-pools-using-tokens-verifying-a-jwt.html)

MiniStackのJWTにはAWS形式のissuerが入ります。今回はそのURLへ公開鍵を取りに行かず、指定したローカル接続先のJWKSを使います。hostsファイルやOSの証明書ストアは変更していません。

これはエミュレーターの基本動作の確認です。Next.jsのログイン画面やAPIの認証・認可は、Day 19で実装します。ブラウザーの認証フロー、PKCE、MFA、SRP、失効、API Gatewayとの連携も今回の確認には含めていません。

## 5. 実AWSに接続しない境界を作る

検証スクリプトは接続先をloopbackの4566/4567番ポートに限定し、外部URLや不明なURLをSDKクライアントの作成前に拒否します。AWSのキーは検証プロセス内で `test` / `test` を明示します。

個人用のAWSプロファイルや設定ファイル、セッショントークンを継承せず、メタデータ認証やHTTPプロキシも使いません。接続に失敗しても実AWSへ切り替える処理はありません。[Boto3の設定資料](https://docs.aws.amazon.com/boto3/latest/guide/configuration.html)

この境界は単体テストでも確認します。

```sh
uv run --project infra/local-aws --locked python -m unittest discover -s scripts -p 'test_*.py' -v
```

4件が成功しました。外部URLの拒否だけでなく、既存のAWSプロファイル・資格情報・endpoint設定・プロキシを渡しても、ローカル用クライアントがそれらを使わないことを確認しています。アプリ側の設定読込と環境の分離は、Day 5で別途実装します。

## 6. コンテナを消して作り直しても保持されるか

永続化は設定を書いただけで確認済みにはせず、次のコマンドでコンテナを操作しました。

```sh
uv run --project infra/local-aws --locked python scripts/verify_local_aws.py --lifecycle
```

この検証では、本プロジェクトのMiniStackを再起動し、さらに `down` → `up` で再作成します。接続は一時的に切れます。結果は次のとおりでした。

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

再作成後も、同じデータとCognitoユーザーを参照でき、再作成前に発行したJWTを同じ公開鍵で検証できました。通常停止での確認であり、強制終了時のデータ保証やバックアップの検証ではありません。

作業を終えるときは次で停止・削除します。名前付きボリュームは残ります。

```sh
docker compose --env-file /dev/null -f compose.yaml down
```

ローカルデータをすべて破棄する場合だけ `down --volumes` を使います。通常の停止とデータ初期化を分けます。[Docker Composeの削除対象](https://docs.docker.com/reference/cli/docker/compose/down/)

## AWSへデプロイするときに同じになるもの・別に確認するもの

標準AWS SDKを使うため、アプリの業務処理と接続先を分けておく方針は維持できます。ただし、MiniStackをそのままAWSへ変換するわけではありません。

AWS環境ではローカル用URLとダミー資格情報を使わず、IAMロール・実サービスのissuer・公開鍵・環境別の設定を使います。IaCでの構築とデプロイはDay 22・23で検証します。今回、どちらの製品についてもAWSへの移行を実証したとは扱いません。

また、DynamoDBのトランザクション・条件式・索引、S3の署名付きURLやCORSなどは、実装するDayで確認します。エミュレーターにAPIがあることと、業務要件を満たすことは別に検証します。[MiniStackの既知の制限](https://ministack.org/docs/limitations)

## まとめと次回

MiniStackとLocalStackを起動し、今回の条件で動作確認できたMiniStackでローカルAWS環境を用意しました。DynamoDB・S3・Cognitoの基本操作、署名検証、状態保持、接続先の分離までを確認できました。

手順と比較条件は [LOCAL_AWS.md](https://github.com/hirolisberger/sales-manager-dashboard/blob/day03/docs/LOCAL_AWS.md)、検証記録は [DAY3_REVIEW.md](https://github.com/hirolisberger/sales-manager-dashboard/blob/day03/docs/DAY3_REVIEW.md) にまとめています。これらのタグURLも承認・マージ・タグ作成後に公開前確認を行います。

Day 3は実装・記事をレビューする段階です。承認を受けてPRをmainへマージしてから、開始指示に従ってDay 4のデータモデルとAPI契約の設計へ進みます。Qiitaへの投稿や公開は、このレビューとは分けて管理します。
