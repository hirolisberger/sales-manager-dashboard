# 【Day 06】MiniStackで永続化する：データアクセス層と初期データ

シリーズ：**Next.js・Python・AWSで作る売上管理システム**

公開予定：2026年12月6日（日本時間）。開発・レビューとQiita公開は別に管理しています。

## はじめに

[Day 5](https://github.com/hirolisberger/sales-manager-dashboard/blob/day05/qiita/day05-fastapi-foundation-and-tests.md)ではFastAPIのヘルスチェックと設定・エラー処理を作りました。今回は、PythonからMiniStackのDynamoDBへデータを保存して読み取る処理を追加します。

**到達点は、保存層・テーブル初期化・架空の商品データ投入・リセットです。** 商品登録や売上登録のHTTP APIは後続Dayで作ります。ブラウザーで商品一覧を見る段階ではないため、CLIの結果と自動テストで確認します。

今回確認するのは、次の四つです。

- 個人のAWS資格情報をローカル操作に使わない
- 初期化とデータ投入を繰り返しても、重複や意図しない上書きを起こさない
- 条件付きの複数項目保存が失敗したとき、途中だけ保存されない
- コンテナを再起動・再作成しても、名前付きボリュームのデータが残る

リポジトリは [sales-manager-dashboard](https://github.com/hirolisberger/sales-manager-dashboard) です。完成版は承認・mainマージ後に[`day06`タグ](https://github.com/hirolisberger/sales-manager-dashboard/tree/day06)で共有します。現在はレビュー待ちで、day06タグは未作成です。

確認日：2026-10-30。macOS ARM64、Python 3.14.9、uv 0.13.6、MiniStack 1.5.33の固定構成で検証しました。以下のコマンドはすべてプロジェクトルートで実行します。`.tools/uv/bin/uv`は今回のuv配置先なので、別の場所に導入した場合は自身の`uv`へ置き換えてください。

## 1. HTTPの処理と保存先の操作を分ける

APIパッケージに次のモジュールを追加しました。

| ファイル | 担当 |
| --- | --- |
| aws.py | 設定に応じたDynamoDBクライアントの生成 |
| repository.py | 取得・Queryの1ページ・条件付きトランザクション・型の変換 |
| bootstrap.py | ローカル用の初期化・架空データ・リセット |
| data_cli.py | 初期化などを明示的に実行するCLI |

リポジトリ層は、保存先の読み書きを引き受ける部分です。後続Dayの商品・売上処理はここを呼び出し、DynamoDBの型付きデータ形式を業務処理の各所へ持ち込まないようにします。

保存層の内部では、店舗別のキーを組み立てます。たとえば商品のPKは`STORE#demo#PRODUCTS`、SKは`PRODUCT#商品UUID`です。店舗IDはサーバー設定の`STORE_ID`から決めます。HTTP要求の本文から店舗を選ばせる実装にはしていません。認証との連携はDay 19の対象です。

初期データもCLIから投入します。API起動や`GET /health`に、テーブル作成・データ投入の副作用はありません。

## 2. ローカル用のSDKを隔離する

Boto3とbotocoreは`1.43.121`をAPIの実行依存へ追加し、ロックを更新しました。Day 3〜4の検証環境と同じSDK版を使います。

local/testでは、接続先を`http://127.0.0.1:4566`または`http://localhost:4566`に限定し、資格情報はダミーの`test / test`を渡します。さらにセッション内の設定で、profileを無効化し、AWSのconfig・credentialsの参照先を`/dev/null`にします。個人の設定ファイルやOS環境変数を書き換える処理ではありません。[Boto3のセッション](https://docs.aws.amazon.com/boto3/latest/guide/session.html)

SDKにはサービス別の接続先設定もあるため、`ignore_configured_endpoint_urls=True`を指定します。ローカルではプロキシも空設定にします。単体テストでは、存在しないprofileや別エンドポイント、ダミーの個人資格情報が環境変数にあっても、ローカル接続先とダミー資格情報が使われ、環境変数が変わらないことを確認しました。[botocore Config](https://docs.aws.amazon.com/botocore/latest/reference/config.html)

AWSモードは標準エンドポイントと通常の資格情報探索を使う設計です。ただし今回の管理CLIはAWSモードをSDK生成前に拒否します。実AWSへの接続・作成・削除はまだ検証していません。

## 3. 初期化とデータ投入を別の操作にする

まず依存を導入し、MiniStackを起動します。

```sh
UV_CACHE_DIR="$PWD/.cache/uv" .tools/uv/bin/uv sync --project apps/api --locked

docker compose --env-file /dev/null -f compose.yaml up -d --wait
```

`--locked`はロックを更新せずに導入する指定です。Composeの`--env-file /dev/null`は暗黙の`.env`読込を避け、`--wait`はヘルスチェックを待ちます。API用の仮想環境はuvが作成・選択するので、手動のactivateは不要です。

次にテーブルを作成します。

```sh
UV_CACHE_DIR="$PWD/.cache/uv" .tools/uv/bin/uv run \
  --project apps/api --locked \
  sales-manager-data --env-file apps/api/.env.example init
```

見本では`DYNAMODB_TABLE=sales-manager-local`、`STORE_ID=demo`です。OS環境変数が見本より優先されるため、出力のtable / storeも確認します。

初回は`created: true`、再実行では`false`になります。テーブルは文字列のPK/SK、PAY_PER_REQUEST、追加索引なしです。既存テーブルの構成が違う場合は、削除・変更せずに停止します。作成後はwaiterで利用可能になるのを待ちます。[CreateTable仕様](https://docs.aws.amazon.com/amazondynamodb/latest/APIReference/API_CreateTable.html)

架空データは別のseedコマンドで投入します。

```sh
UV_CACHE_DIR="$PWD/.cache/uv" .tools/uv/bin/uv run \
  --project apps/api --locked \
  sales-manager-data --env-file apps/api/.env.example seed

UV_CACHE_DIR="$PWD/.cache/uv" .tools/uv/bin/uv run \
  --project apps/api --locked \
  sales-manager-data --env-file apps/api/.env.example inspect
```

商品2件、商品コード予約2件、投入版マーカー1件の計5項目を同じトランザクションで保存します。初回は`seeded: true`、全項目が同じままの再実行は`false`です。

inspectは商品だけを読むため、`product_count: 2`になります。COFFEEは550円、TEAは330円、versionはそれぞれ1です。固定UUID・架空日時の商品だけで、売上はまだ投入しません。

変更済みや一部だけ存在するデータにseedを実行した場合は、終了コード1で停止します。初期値へ戻すために商品価格を上書きする処理は設けません。

## 4. 複数項目を途中まで保存しない

商品本体と商品コード予約が別々に保存されると、重複コードだけが残ったり、予約なしの商品ができたりします。今回は、条件付きPut等を`TransactWriteItems`へまとめる仕組みを作りました。[AWSのトランザクション仕様](https://docs.aws.amazon.com/amazondynamodb/latest/APIReference/API_TransactWriteItems.html)

実際のMiniStackでは、既存コードの予約を含む書込を失敗させ、同時に追加しようとした別項目も保存されないことを確認しました。古いversionを条件にした操作も、全体が失敗します。

保存層には、同じ項目への二重操作、他店舗のキー、小数を含むデータを拒否するガードを付けました。取得時の整数はPythonのintに戻し、小数を整数へ切り捨てません。55アクション・1項目256KiB・要求全体3MiBというDay 4の保守的な容量ガードも適用します。これはAWSの正確なサイズ計算の代わりではありません。

ページングはQueryの1ページと継続キーを返すところまでです。Limitは評価件数なので、空ページでもキーがあれば続ける扱いにします。HTTP用の署名付きカーソルや、商品一覧の返却件数を満たす処理は後続Dayで追加します。[Query仕様](https://docs.aws.amazon.com/amazondynamodb/latest/APIReference/API_Query.html)

## 5. 保持とリセットを分ける

Day 3の名前付きボリュームを使っているため、通常のrestartやdown / upではデータを残します。検証用テーブルの5項目について、再起動・再作成の前後で内容のハッシュが一致しました。

リセットは明示的な別コマンドです。次は**sales-manager-localテーブル内の全店舗・全データを削除して空に戻す操作**なので、データを残す場合は実行しません。

```sh
UV_CACHE_DIR="$PWD/.cache/uv" .tools/uv/bin/uv run \
  --project apps/api --locked \
  sales-manager-data --env-file apps/api/.env.example \
  reset --confirm-table sales-manager-local
```

確認名が対象テーブルと一致しない場合は停止します。成功後も自動でseedは実行しません。他テーブル・S3・Cognito・ボリュームは削除しない構成です。

通常の終了は次のコマンドです。`-v`を付けず、名前付きボリュームを残します。

```sh
docker compose --env-file /dev/null -f compose.yaml down
```

## 6. 今回の確認結果

単体テストと実際のMiniStackでの確認を分けて実行します。

```sh
UV_CACHE_DIR="$PWD/.cache/uv" .tools/uv/bin/uv run \
  --project apps/api --locked pytest apps/api/tests -q

UV_CACHE_DIR="$PWD/.cache/uv" .tools/uv/bin/uv run \
  --project apps/api --locked python scripts/verify_day06_persistence.py
```

結果は単体テスト88件成功、MiniStackの検証10項目成功です。後者は一意名の専用テーブルだけを作成・削除し、`temporary_table_deleted: true`を返します。既存の検証名を指定した場合は変更せず停止します。

別途、実CLIのinit・seed・inspect・resetと拒否時の終了コード、再起動・再作成後の保持、Ruff、既存のAPI仕様検証6グループ、配布物作成と実行用依存だけのwheel読込を確認しました。

SDKの通信なしのテストでAWS用クライアントの接続先は確認していますが、実AWSへの移行・IAM・負荷性能は未検証です。MiniStackでの成功を実AWSとの完全な互換性保証にはしません。

## まとめと次回

Day 6では、保存層と明示的な初期化・seed・resetを作り、再実行時の上書き拒否とデータ保持を確認しました。次のDay 7で、この保存層を使って商品マスタのHTTP APIを作ります。

Day 6の実装とこの記事はレビュー待ちです。承認・mainマージと開始指示を受けてからDay 7へ進みます。各コマンドの詳しい説明は[DAY6_COMMANDS.md](https://github.com/hirolisberger/sales-manager-dashboard/blob/day06/docs/DAY6_COMMANDS.md)、仕様は[PERSISTENCE.md](https://github.com/hirolisberger/sales-manager-dashboard/blob/day06/docs/PERSISTENCE.md)、結果は[DAY6_REVIEW.md](https://github.com/hirolisberger/sales-manager-dashboard/blob/day06/docs/DAY6_REVIEW.md)にまとめます。これらのday06リンクはタグ作成後に参照可能になります。
