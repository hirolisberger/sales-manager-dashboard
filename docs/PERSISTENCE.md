# Day 6：MiniStackへの保存と初期データ

2026-10-30作成。Day 5の承認・[PR #4](https://github.com/hirolisberger/sales-manager-dashboard/pull/4)マージと[day05タグ](https://github.com/hirolisberger/sales-manager-dashboard/tree/day05)を確認して、main `2a1354f`から着手した。Day 6は2026-10-30にレビュー承認済み（対象c5d4c9d）。HTTPの実装済みルートは引き続き`GET /health`だけ。

## 実装した責務

| ファイル（apps/api/src/sales_manager_api/配下） | 担当 |
| --- | --- |
| `aws.py` | 設定を受け取り、ローカル専用またはAWS用のDynamoDBクライアントを生成 |
| `repository.py` | 店舗内のキー、強い整合性の取得・Queryの1ページ、条件付きトランザクション、型と容量のガード |
| `bootstrap.py` | ローカル専用のテーブル作成・構成確認・架空データ投入・リセット |
| `data_cli.py` | 明示的なinit / seed / inspect / resetコマンド |
| `settings.py` | 既存設定にDYNAMODB_TABLEとSTORE_IDを追加 |

HTTPや金額計算の処理から保存先の操作を分けた。リポジトリが受け取るのはPythonの辞書で、DynamoDBのAttributeValueへの変換は内部で行う。API起動やhealthではクライアント生成・テーブル作成・seedを実行しない。商品登録の業務検証・HTTP APIはDay 7、売上の保存計画はDay 8以降で追加する。

## SDKと接続境界

Boto3とbotocoreはともに`1.43.121`をAPIの実行依存へ固定した。Day 3〜4の検証環境と同じSDK版を使い、API用の`uv.lock`を更新した。検証専用の`infra/local-aws`の依存とロックは変更していない。最新版であるという意味ではない。

| 設定 | local / test | aws |
| --- | --- | --- |
| 接続先 | HTTPの127.0.0.1 / localhost:4566だけ。未指定時127.0.0.1 | 明示したリージョンの標準DynamoDBエンドポイント |
| 資格情報 | ダミーのtest / test。セッショントークンは空 | SDK標準の資格情報探索。実行ロール等は配備時に検証 |
| 個人のAWS設定 | セッション内でprofileを無効化し、config・credentialsの参照先を/dev/nullへ設定 | 通常の探索を利用 |
| 環境変数等の別エンドポイント | ignore_configured_endpoint_urls=Trueで使わない | 同左。AWS_ENDPOINT_URL自体の指定は設定検証で拒否 |
| プロキシ | 空設定。ローカル呼出しをプロキシへ送らない | SDKの通常設定 |
| 管理CLI | 専用名のテーブルのみ許可 | SDK生成前に拒否 |

上記はこのファクトリーから作るDynamoDBクライアントの境界。OS環境変数・個人のAWS設定ファイル・シェル設定は変更しない。botocoreのセッション内ConfigValueStoreを利用するため、SDK更新時には境界テストを再実行する。[Boto3のセッション](https://docs.aws.amazon.com/boto3/latest/guide/session.html)、[botocore Config](https://docs.aws.amazon.com/botocore/latest/reference/config.html)

タイムアウトは接続2秒・読取5秒、SDKの試行回数は1回。曖昧な通信失敗の再送・HTTPの冪等性処理はここで代替しない。AWSモードはネットワークを使わない単体テストで接続先だけ確認し、実AWSへの接続・作成・削除は未実施。

## 設定とテーブル

`DYNAMODB_TABLE`の既定値は`sales-manager-local`。`STORE_ID`はサーバー設定で既定`demo`、小文字英数字とハイフンの1〜32文字。本文やカーソルから店舗を切り替えない。認証による店舗・利用者の確定はDay 19で追加する。

管理CLIはAPP_ENVがlocal/test、テーブル名が`sales-manager-local` / `sales-manager-test`またはそれらに`-小文字英数字等`を付けた名前の場合だけ実行できる。awsモード・無関係なテーブル名・reset確認名不一致はクライアント生成前に停止する。

テーブルは文字列のPK/SK、PAY_PER_REQUEST、GSI/LSIなし。initは未作成なら作成してwaiterで待つ。既存なら構成を照合して利用し、異なる構成なら変更せずに停止する。データ投入・削除・自動移行はinitに含めない。[CreateTable仕様](https://docs.aws.amazon.com/amazondynamodb/latest/APIReference/API_CreateTable.html)

## リポジトリの境界

- `get`はConsistentRead=True。不存在はNone。
- `query_page`は同一店舗・パーティションとSKの前方一致を使い、1ページとLastEvaluatedKeyを返す。Limitは1〜100の評価件数で、HTTPの返却件数を保証するものではない。継続キーがあれば空ページでも終了とみなさない。inspectはキーがなくなるまで読む。外部用カーソルの署名・期限はDay 9。
- `transact`はPut / Delete / ConditionCheckをまとめる。各操作は条件式必須、同一項目への二重操作と他店舗キーを拒否。Update式ではなく、条件付きPutによる置換も利用できる。
- 保存値は文字列・整数・bool・null・配列・文字列キーの辞書。float、入力側のDecimal、set、bytes等を拒否する。取得した整数のDecimalはintへ戻し、保存済みの小数は切り捨てずエラーにする。
- 上限は55アクション、型付きJSONの1項目256KiB・要求全体3MiB。これはDay 4の保守的なガードであり、AWSの厳密な項目サイズ計算ではない。
- 条件不一致・競合はStorageConflict、それ以外のSDK障害はStorageError。トランザクション取消の理由が不明なら通常障害として扱い、認可失敗・容量不足等を重複エラーに誤分類しない。SDKの本文・資格情報・入力値を例外メッセージへ転載しない。

強い整合性でも、複数ページを横断したスナップショットは保証しない。業務上の入力上限・金額計算・売上履歴・再送応答の保存は、後続Dayのサービスがこの保存層を使って実装する。[Query仕様](https://docs.aws.amazon.com/amazondynamodb/latest/APIReference/API_Query.html)、[トランザクション仕様](https://docs.aws.amazon.com/amazondynamodb/latest/APIReference/API_TransactWriteItems.html)

## 架空データと保持方針

seedはコーヒー550円・紅茶330円の商品2件、コード予約2件、投入版マーカー1件の計5項目を同じトランザクションで保存する。固定UUIDと架空のUTC日時を使い、実売上や実在利用者は含めない。売上の初期データは今回投入しない。

全5項目が初期値と同じならseedの再実行は何もしない。1項目でも変更済み・部分的に存在する場合は上書きせず停止する。同時実行でも存在しない条件を満たす側だけが保存し、同じデータが先に確定した場合は再読込して完了とする。このマーカーはHTTPの要求キー・冪等性記録の代用ではない。

Composeは既存の名前付きボリュームを使用。restartや通常のdown / upでは保持する。resetは**指定テーブルの全項目・全店舗**を消して同じ構成の空テーブルへ戻す。--confirm-tableに正確な名前を要求し、自動seedはしない。S3・Cognito・他テーブル・ボリュームをまとめて消さない。通常の片付けに`down -v`を使わない。

操作と各指定の解説は [DAY6_COMMANDS.md](DAY6_COMMANDS.md)、検証結果と制限は [DAY6_REVIEW.md](DAY6_REVIEW.md)。公式資料確認日は2026-10-30。
