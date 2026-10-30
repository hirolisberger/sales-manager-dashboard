# 【Day 04】売上データとAPIを設計する：DynamoDBのキーと更新契約

シリーズ：**Next.js・Python・AWSで作る売上管理システム**

公開予定：2026年12月4日（日本時間）。開発・レビューとQiitaへの公開は別に管理しています。

## はじめに

[Day 3](https://github.com/hirolisberger/sales-manager-dashboard/blob/day03/qiita/day03-ministack-localstack-local-aws.md)では、ローカルAWS環境としてMiniStackを採用しました。今回は、商品・売上・明細・履歴をどう保存し、画面からどのAPIで扱うかを設計します。

今回の方針は、**売上に明細を埋め込み、最新版・日付別参照・履歴・再送用の記録をDynamoDBのトランザクションで保存する**ことです。日付で検索するデータも同時に更新し、訂正直後の集計を非同期のインデックスだけに依存させない構成にします。

成果物は設計資料、OpenAPI、架空データ、実行できる設計確認スクリプトです。HTTP APIや画面はまだ動きません。APIの土台はDay 5、製品用の保存処理はDay 6以降に作ります。

## この記事の到達点

- 商品・売上・履歴の関係と、取引時の値を保存する理由を説明する
- 日付検索・集計・訂正をDynamoDBのキーへ対応させる
- 入力、更新競合、再送、エラーのAPI契約を決める
- MiniStackで一括保存と失敗時の整合性を確認する

リポジトリは [sales-manager-dashboard](https://github.com/hirolisberger/sales-manager-dashboard) です。この回の完成版は [`day04`タグ](https://github.com/hirolisberger/sales-manager-dashboard/tree/day04) で共有する予定です。レビュー承認・mainマージ前のため、現時点でタグは未作成です。以降の文書リンクも同タグを前提とし、Qiita公開前に存在を確認します。

公式資料の確認日は2026-10-30。実行環境はmacOS ARM64、Python 3.14.9、uv 0.13.6、Docker 29.1.2、MiniStack 1.5.33です。Day 3のdigest固定Composeを使います。

## 1. 商品の値と取引時の値を分ける

売上明細には商品IDだけでなく、販売した時点の商品コード・名称・税込単価も保存します。

たとえば550円で売ったコーヒーの標準単価を600円にしても、過去の売上は550円です。商品を無効化しても、その商品を含む売上の履歴は残ります。

| データ | 保存する内容 |
| --- | --- |
| 商品 | コード、名称、税込標準単価、有効状態、版 |
| 売上 | 計上日、状態、版、明細、確定した合計 |
| 明細 | 商品IDと取引時の値、整数数量、明細金額 |
| 履歴 | 変更前後、理由、認証済み操作者、操作日時 |

単価は0〜9,999,999円、数量は1〜9,999、明細は最大50件、売上合計は9,999,999,999円以下です。小数は丸めずエラーにします。

```text
明細金額 = 取引時の税込単価 × 整数数量
売上合計 = 明細金額の合計
```

明細を訂正する場合も、同じ商品なら旧名称を保持します。商品を差し替えた場合や、現在の商品情報を取り直す指定をした場合だけ、新しいスナップショットを作ります。単価と数量は訂正要求の値を使い、現在の標準単価で自動的に置き換えません。

## 2. 読みたい操作からキーを決める

このシステムでは、商品一覧、売上詳細、期間一覧、履歴、日別・月別・商品別集計が必要です。初期構成は`PK`と`SK`を持つ単一テーブルとし、次の項目を置きます。`demo`は架空店舗です。

| 用途 | PK | SK |
| --- | --- | --- |
| 商品 | `STORE#demo#PRODUCTS` | `PRODUCT#{商品ID}` |
| コード重複防止 | `STORE#demo#PRODUCT_CODES` | `CODE#{商品コード}` |
| 売上最新版 | `STORE#demo#SALE#{売上ID}` | `CURRENT` |
| 売上履歴 | 同じ売上PK | `REV#{10桁の版}` |
| 日付別参照 | `STORE#demo#DAY#{計上日}` | `SALE#{売上ID}` |
| 再送用の記録 | `STORE#demo#REQUEST#{操作者}` | `KEY#{要求ID}` |

最新版と日付別参照の両方に、明細を含む売上全体を保存します。重複保存する分の容量は増えますが、日付別参照を読むだけで商品フィルターや集計、CSVの対象明細を選べます。

期間一覧は日付の新しい順にQueryし、同じ日では売上IDの降順に並べます。同じ日の登録時刻順ではありません。詳細は売上IDでGetItem、履歴は`REV#`でQueryします。初期設計でScanやGSIは使いません。

## 3. 関係する項目をまとめて確定させる

売上を登録したのに日付検索には出ない、あるいは訂正したのに旧金額が残る状態を避けるため、関連項目を一括保存します。

```text
登録：最新版 + 履歴 + 日付別参照 + 冪等性記録
別日への訂正：最新版 + 履歴 + 旧日参照の削除 + 新日参照 + 冪等性記録
取消：最新版 + 履歴 + 日付別参照 + 冪等性記録
```

必要な場合は、選択した商品の版と有効状態のConditionCheckも加えます。確認後に商品が無効化された場合は、売上の一部だけを保存せずトランザクション全体を失敗させます。同じ商品への確認は1回にまとめます。

AWSのTransactWriteItemsには、100の異なる項目・合計4MiBなどの上限があります。明細50件を別項目にすると最新版と日付別の複製だけで項目数が膨らむため、今回は売上の中に配列として明細を保持します。50種類の商品を含む場合でも、登録は最大54、別日訂正は最大55アクションに収まる設計です。[AWSトランザクション仕様](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/transaction-apis.html)

1項目400KiBという制限もあるため、件数だけでは不十分です。設計用スクリプトでは型付きJSONの大きさを保守的に測り、1項目256KiB・要求全体3MiB以内を確認します。この測定値はAWSの厳密なサイズ計算そのものではありません。[AWSの制限](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/Constraints.html)

## 4. 空の検索結果でも次ページがある

DynamoDBのQueryでは、`Limit`や1MiBの区切りまで項目を評価してからフィルターを適用します。そのため、次の状態があり得ます。

```text
Items = []
LastEvaluatedKey = 次の読み取り位置
```

今回も`Limit=1`で、最初に読んだ取消済み売上が除外されるケースをMiniStackで再現できました。空だから終わりにすると、後ろの有効な売上を読み落とします。`LastEvaluatedKey`がなくなるまで続ける必要があります。[AWS Query仕様](https://docs.aws.amazon.com/amazondynamodb/latest/APIReference/API_Query.html)

API側のlimitは返す件数です。内部のQueryを複数回実行することや、次の日付へ進むことを含めて設計します。公開するカーソルには条件との結び付け・期限・改ざん検証を持たせる予定で、製品実装はDay 9です。

## 5. 更新競合と再送を別々に扱う

APIの設計では次を使います。

| 目的 | 契約 |
| --- | --- |
| 古い画面からの上書きを防ぐ | 詳細取得のETagをIf-Matchに指定する |
| 同じ要求の二重登録を防ぐ | POST/PATCHにIdempotency-Keyを指定する |
| 訂正前後を追う | 同じ売上IDの版を増やして履歴を追加する |

If-Matchがない更新は428、現在版と合わない初回更新は412にします。コード重複、取消済み売上の再訂正、違う内容での要求キー再利用は409です。[RFC 9110](https://www.rfc-editor.org/rfc/rfc9110.html#name-if-match)、[RFC 6585](https://www.rfc-editor.org/rfc/rfc6585.html#section-3)

再送用の記録には最初の成功応答を残します。登録後に880円へ訂正していても、最初の1,430円の登録要求を再送したら、その登録時の応答を返す契約です。現在の金額は改めてGETで取得します。

Day 4では、この記録が更新後も残ることと、同じキーの二重保存が他項目を巻き込んで失敗することを確認しました。HTTPでのハッシュ比較・認証・再送応答は、これから実装します。

## 6. OpenAPIで入力と応答を共有する

API契約はOpenAPI 3.1.0のJSONにしました。主な操作は次のとおりで、ヘルスチェックや履歴などを含めて15操作あります。

| パス | 主な操作 |
| --- | --- |
| `/products` | 一覧・登録 |
| `/products/{product_id}` | 詳細・名称/価格/利用可否の更新 |
| `/sales` | 期間検索・登録 |
| `/sales/{sale_id}` | 詳細・訂正 |
| `/sales/{sale_id}/cancel` | 取消 |
| `/reports/sales` | 日別・月別集計 |
| `/reports/products` | 商品別集計 |
| `/exports/sales` | CSVジョブ受付（将来実装） |

単価・数量の範囲、明細数、必須の訂正理由、未知フィールドの拒否、共通エラー形式も定義しました。ただし、期間の前後関係や未来日の判定、金額の掛け算はスキーマだけでは完結しません。API側の業務検証も必要です。

またJSON Schemaのintegerだけでは、数学的には整数の`1.0`まで拒否できません。今回の確認では厳格な整数型チェッカーを追加し、本APIにも同じ方針の検証を入れることにしました。スキーマ検証の成功と、実際のHTTP入力を検証したことは分けます。

## 7. 自分の環境で確認する

プロジェクトルート`sales-manager-dashboard/`で実行します。Day 2のuvとPython、Day 3のDocker環境が必要です。以下はプロジェクト内のuvを使う例で、グローバルにuvを準備した場合は`.tools/uv/bin/uv`を`uv`に置き換えられます。

```sh
UV_CACHE_DIR="$PWD/.cache/uv" .tools/uv/bin/uv sync \
  --project infra/local-aws --group contracts --locked

UV_CACHE_DIR="$PWD/.cache/uv" .tools/uv/bin/uv run \
  --project infra/local-aws --group contracts --locked \
  python scripts/verify_day04_contract.py
```

契約、入力拒否、スナップショット、金額とCSV、保存上限など**6テストグループが成功**しました。新しい検証依存はアプリ側へ追加せず、ローカルAWS検証用の任意グループ`contracts`に固定しています。

MiniStackへの保存確認は次のとおりです。

```sh
docker compose --env-file /dev/null -f compose.yaml up -d --wait --wait-timeout 90

UV_CACHE_DIR="$PWD/.cache/uv" .tools/uv/bin/uv run \
  --project infra/local-aws --group contracts --locked \
  python scripts/verify_day04_dynamodb.py

docker compose --env-file /dev/null -f compose.yaml down
```

接続先は`127.0.0.1:4566`に固定され、ダミー資格情報を使います。一意名の一時テーブルを作り、正常終了・検証失敗のどちらでも削除を試みます。処理自体を強制終了した場合は削除できない可能性があるため、`day04-design-`で始まる自分の検証テーブルを確認してください。既存の名前付きボリュームは削除しません。

保存確認では**10項目が成功**し、一時テーブルの削除も完了しました。50種類の商品・50明細では、54アクションの登録と55アクションの別日訂正も成功しています。

## 8. 集計の期待値と残る課題

架空の時計を2027年1月5日に固定し、Day 1の例を使いました。実際の開発日やPCの時計を変更したものではありません。

| 操作 | 12月の合計 |
| --- | --- |
| 3件を登録 | 2,640円 |
| S001のコーヒーを2個から1個に訂正 | 2,090円 |
| S002を取消 | 1,430円 |
| S001の計上日を翌年1月1日へ訂正 | 550円（1月へ880円が移る） |

取消後の紅茶フィルターは330円、CSV対象は3明細・1,430円です。紅茶を含む売上全体の880円を、紅茶だけの売上として加算しないことも確認しました。

この設計の強い整合性は、複数のQueryを一つの過去時点へ固定する保証ではありません。同時更新がなければ画面・集計・CSVを一致させる、という初期条件です。366日分を読むコスト、ページ間の同時更新、事前集計、CSVワーカー、実AWSでの挙動は後続Dayで確認します。

詳細は完成版の[保存設計](https://github.com/hirolisberger/sales-manager-dashboard/blob/day04/docs/DATA_MODEL.md)、[API契約](https://github.com/hirolisberger/sales-manager-dashboard/blob/day04/docs/API_CONTRACT.md)、[検証記録](https://github.com/hirolisberger/sales-manager-dashboard/blob/day04/docs/DAY4_REVIEW.md)にまとめます。これらはday04タグの作成後に参照可能になります。

## まとめと次回

今回は売上のデータモデルをキーとトランザクションへ落とし込み、APIの入力・更新・再送・エラー契約を決めました。MiniStackで設計を試すことで、日付訂正と空ページの扱いを確認できました。

Day 4の設計・検証・記事をレビューしてから、Day 5でPython APIの土台を作ります。レビュー承認前には次のDayへ進みません。Qiitaへの公開予定日は2026年12月4日で、投稿・予約操作は別途行います。
