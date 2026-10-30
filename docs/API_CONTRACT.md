# Day 4：API仕様書

Day 4の設計は2026-10-30に承認済み（対象21307cc）。正本はYAML形式の[OpenAPI 3.1.0](contracts/openapi.yaml)。**Day 5でGET /healthと共通エラー基盤を実装し、要求IDヘッダーと共通500応答を仕様へ追加した。追加分も2026-10-30にDay 5でレビュー承認済み（対象6f52323）。** Day 7で商品4操作・商品のETag/再送/署名付きカーソルを実装した。実装済みはhealthと商品で、売上・認証・CSVは後続Day。[商品APIの仕様](PRODUCT_API.md)と[確認記録](DAY7_REVIEW.md)へ分ける。[保存設計](DATA_MODEL.md)、[架空データ](examples/day04-fixtures.json)、[API基盤の仕様](API_FOUNDATION.md)を参照する。

仕様の編集対象は`docs/contracts/openapi.yaml`に統一し、JSON版は置かない。検証スクリプトはPyYAML 6.0.3の`yaml.safe_load`で読み込み、同じOpenAPI・JSON Schema検証へ渡す。HTTP応答コードのキー（例`'200'`）や型名`'null'`は文字列として引用符を保つ。転記時にYAMLの数値・nullへ変換しない。[PyYAML公式資料](https://pyyaml.org/wiki/PyYAMLDocumentation)

## エンドポイント

| メソッド・パス | 用途・成功応答 |
| --- | --- |
| GET /health | 匿名ヘルスチェック、200 |
| GET /products | 商品一覧、200・items/next_cursor |
| POST /products | 商品登録、201・Product |
| GET /products/{product_id} | 商品詳細、200・Product |
| PATCH /products/{product_id} | 名称・標準単価・利用可否の部分更新、200・Product |
| GET /sales | 期間・商品・状態で絞った一覧、200・items/next_cursor |
| POST /sales | 売上登録、201・Sale |
| GET /sales/{sale_id} | 売上詳細、200・Sale |
| PATCH /sales/{sale_id} | 計上日・明細全体・理由による訂正、200・Sale |
| POST /sales/{sale_id}/cancel | 理由を付けた取消、200・Sale |
| GET /sales/{sale_id}/revisions | 変更履歴、200・items/next_cursor |
| GET /reports/sales | 期間・商品・group_by=day/monthの集計、200 |
| GET /reports/products | 同じ条件の商品別集計、200 |
| POST /exports/sales | 同じ条件のCSVジョブ受付、202・ExportJob |
| GET /exports/{job_id} | 状態・完了後の期限付き取得URL、200・ExportJob |

商品コード・売上IDは変更不可。DELETEは設けない。商品更新の本文は最低1項目。売上訂正の本文は`sale_date`、1〜50件の`lines`、空白だけでない`reason`をすべて必須にし、任意項目の部分更新とは分ける。取消理由も必須。

## 共通の境界

- JSONの未知フィールドを拒否する。金額・数量・版は厳密な整数とし、`1.0`、bool、数値文字列も拒否する。
- JSON Schemaの`integer`だけでは`1.0`の字句まで拒否できない。設計検証には厳格な型チェッカーを追加した。Day 5で厳格な共通モデルと試験用HTTPルートを検証し、商品・売上の具体的な入力モデルは各Dayで実装する。
- サーバーが明細ID・商品スナップショット・金額・状態・版・操作者・日時を確定する。クライアントは合計や操作者を指定できない。
- 日付は`YYYY-MM-DD`、時刻はUTCのタイムゾーン付きISO 8601、IDはUUID。版は1〜2,147,483,647で上限到達時は更新を拒否する。
- 商品単価・売上合計の上限は[保存設計](DATA_MODEL.md)を参照。集計結果もJavaScriptの安全な整数上限9,007,199,254,740,991を超えたらエラーにし、精度を落として返さない。
- `/health`以外は最終形でBearer JWTと管理者権限を必須にする。認証はDay 19に実装する。それまではローカルだけの開発構成とし、未認証の業務APIを実AWSへ公開しない。

## 絞り込み・集計・ページング

売上一覧・集計・CSVでは`start_date`と`end_date`を必須にする。終了日を含む1〜366日を指定でき、検索には未来を含む期間も使える。登録・訂正の計上日はJST本日以前に限る。年9999の末日など、翌日を表現できない終了日は範囲エラーにする。実装時にこれらの相関条件を検証する。

売上一覧の`status`は`all`（既定）・`confirmed`・`cancelled`。集計とCSVはconfirmedに固定する。`product_id`指定時は対象明細だけの金額・数量を使う。一覧の`total_amount_yen`は元の売上全体、`matched_amount_yen`と`matched_quantity`は絞り込み後を示す。詳細のlinesは常に全明細。

一覧・履歴の`limit`は1〜100、既定50。空のitemsとnullのnext_cursorが終端。無効・改ざん・期限切れ・他条件のカーソルは400とする。内部QueryのページングとAPIのページングは同じではない。[保存設計のページング](DATA_MODEL.md#ページング)を実装する。

売上集計は金額・数量・重複を除いた売上件数と、日別/月別の0補完済みrowsを返す。商品別は商品IDをキーにし、複数商品の売上件数を単純合計しない。複数リクエストにまたがる同時更新時のスナップショットは保証しない。

## 更新前提条件と冪等性

すべてのPOST/PATCHでUUIDの`Idempotency-Key`を必須にする。商品PATCH・売上PATCH・取消POSTでは、直前の詳細取得で受け取った強いETag（例`"v1"`）を`If-Match`へ渡す。単一のこの形式だけを受け付け、ワイルドカードや弱いETagは受け付けない。

```http
PATCH /sales/00000000-0000-4000-8000-000000000003
Content-Type: application/json
If-Match: "v1"
Idempotency-Key: 00000000-0000-4000-8000-000000000099
```

成功応答には更新後のETagを返す。再送は同じ要求キー・本文・パス・メソッド・If-Matchなら、**最初に保存した成功応答**を元のステータスとETagで返し、`Idempotency-Replayed: true`を付ける。既に後から訂正されていても再送応答を現在版に差し替えない。現在状態はGETで取得する。

要求内容が違うキー再利用は409、初回要求のIf-Match不一致は412、必須If-Match不足は428。認証・権限の確認は再送時も必須。商品のHTTP再送・要求の正規化・版条件はDay 7で実装した。認証前はサーバー固定のlocal-adminを使い、local/test専用とする。売上側は後続Day。Day 4の記録保存検証とは区別する。[RFC 9110](https://www.rfc-editor.org/rfc/rfc9110.html#name-if-match)、[RFC 6585](https://www.rfc-editor.org/rfc/rfc6585.html#section-3)

## エラー形式

```json
{
  "error": {
    "code": "VERSION_CONFLICT",
    "message": "売上が更新されています。再取得してください。",
    "request_id": "00000000-0000-4000-8000-000000000090",
    "details": []
  }
}
```

| HTTP | 主なコード・条件 |
| --- | --- |
| 400 | INVALID_JSON / INVALID_CURSOR / INVALID_HEADER |
| 401 | UNAUTHENTICATED。WWW-Authenticateも返す |
| 403 | FORBIDDEN |
| 404 | NOT_FOUND（Day 5の不明パス）/ PRODUCT_NOT_FOUND / SALE_NOT_FOUND / EXPORT_NOT_FOUND |
| 405 | METHOD_NOT_ALLOWED。Allowを保持 |
| 409 | PRODUCT_CODE_CONFLICT / IDEMPOTENCY_CONFLICT / PRODUCT_INACTIVE / SALE_CANCELLED / VERSION_LIMIT_EXCEEDED（商品の版上限） |
| 412 | VERSION_CONFLICT。取得していない商品の内部版競合は再検証し、必要なら409へ変換する |
| 422 | VALIDATION_ERROR / PERIOD_TOO_LONG / FUTURE_SALE_DATE / AMOUNT_LIMIT_EXCEEDED |
| 428 | PRECONDITION_REQUIRED |
| 503 | TEMPORARILY_UNAVAILABLE / QUERY_BUDGET_EXCEEDED。再試行可能な場合はRetry-After |
| 500 | INTERNAL_ERROR。内部の例外メッセージを返さない |

detailsの各要素は`path`、`code`、`message`。内部スタック、トークン、AWS資格情報や入力全体をエラーへ返さない。OpenAPIの共通エラー応答は候補集合で、全操作がすべてのエラーを発生させる意味ではない。

## CSVジョブの仕様と未実装範囲

受付時は検索条件を固定し202を返す。queued → running → completed/failedを想定し、完了時だけ期限付きdownload_url/expires_atを設定する。出力内容は明細単位、対象条件・生成日時を記録する。同時更新で整合性を保てなかった場合の再試行・失敗、URL期限とジョブ保持期間はDay 17で確定する。スキーマだけでは状態とnull項目の相関を保証しないため、ワーカーの検証も追加する。

Day 7時点のHTTP実装はhealthと商品4操作。全応答のX-Request-ID、商品のETag・再送・署名付き一覧継続を実装した。認証・売上・非同期ワーカー・S3 URLは未実装。YAMLのBearerAuthは最終設計であり、現在の商品APIはlocal/test専用でawsモードでは拒否する。

## 検証資料

[DAY4_REVIEW.md](DAY4_REVIEW.md)にコマンド・期待値・確認範囲を記録する。仕様は[OpenAPI 3.1.0仕様](https://spec.openapis.org/oas/v3.1.0.html)に従う。確認日は2026-10-30。
