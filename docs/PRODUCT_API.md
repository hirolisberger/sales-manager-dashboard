# Day 7：商品マスタAPI

2026-10-30作成。Day 6の承認・[PR #5](https://github.com/hirolisberger/sales-manager-dashboard/pull/5)マージと[day06タグ](https://github.com/hirolisberger/sales-manager-dashboard/tree/day06)を確認し、main `b92b01f`から着手した。Day 7は実装・記事・検証完了、レビュー待ち。

## 実装した範囲

| 操作 | 成功応答 |
| --- | --- |
| POST /products | 201、商品、ETag、Idempotency-Replayed |
| GET /products | 200、items / next_cursor。is_active・limit・cursorを指定可能 |
| GET /products/{product_id} | 200、商品、ETag。無効商品も取得可能 |
| PATCH /products/{product_id} | 200、更新後の商品、ETag、Idempotency-Replayed |

healthと合わせて5操作を実装した。商品画面・売上API・認証は後続Day。DELETEは設けず、`is_active=false`で無効化する。trueへの変更で同じ商品を再有効化できるが、無効化中も商品コードの予約を保持し、別商品への再利用を拒否する。

`product_models.py`が厳格な入出力、`products.py`が業務操作・保存計画、`product_routes.py`がHTTPと依存の生成・終了、`cursors.py`が商品一覧の継続情報を担当する。Day 6のDynamoRepositoryを再利用し、新しいDB・SDK依存は追加していない。同期ルートからSDKを呼び、依存のyield/finallyでクライアントを閉じる。[FastAPI公式](https://fastapi.tiangolo.com/tutorial/dependencies/dependencies-with-yield/)

## 入力・版・日時

商品登録はcode・name・default_unit_price_yenが必須。コードは大文字英数字で始まる1〜32文字で、後続は大文字英数字・ハイフン・アンダースコア。名称は空白だけを除く1〜100文字で、前後の空白を自動削除しない。税込単価は0〜9,999,999の厳格な整数で、float・bool・文字列からの変換はしない。[Pydantic strict mode](https://docs.pydantic.dev/latest/concepts/strict_mode/)

PATCHはname・default_unit_price_yen・is_activeのうち1項目以上。null、空の本文、code/id/version/操作者等の指定、未知フィールドを拒否する。versionは登録時1、成功した更新ごとに1増え、上限2,147,483,647では409 VERSION_LIMIT_EXCEEDED。同じ値を指定した更新も版を増やす。商品ID・コード・created_atは変更しない。日時はサーバーのUTC時計から設定する。

## 更新条件と再送

POST/PATCHに単一UUID形式のIdempotency-Keyが必須。PATCHには単一の強いETag（`"v1"`等）をIf-Matchへ渡す。ワイルドカード・弱いETag・複数ヘッダー・上限外の版は拒否する。

| 条件 | 応答 |
| --- | --- |
| 要求キーが未指定・不正、If-Matchの形式不正 | 400 INVALID_HEADER |
| PATCHでIf-Match不足 | 428 PRECONDITION_REQUIRED |
| 初回更新の版不一致・並行更新で旧版になった | 412 VERSION_CONFLICT |
| 商品コード重複 | 409 PRODUCT_CODE_CONFLICT |
| 同じ要求キーを別内容・別操作・別If-Matchで使用 | 409 IDEMPOTENCY_CONFLICT |
| 商品なし | 404 PRODUCT_NOT_FOUND |
| 入力・UUIDパス・検索条件の不正 | 422 VALIDATION_ERROR |
| DB障害 | 503 TEMPORARILY_UNAVAILABLE、Retry-After: 1 |

登録は商品・コード予約・最初の成功応答の3項目、更新は旧版条件付き商品・成功応答の2項目を同じトランザクションで確定する。失敗時は部分保存しない。SDKのトークンだけで再送を識別しない。[DynamoDB公式](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/transaction-apis.html)

要求記録は店舗・操作者・要求キーに結び付け、メソッド・正規化パス・正規化JSON本文・If-MatchのSHA-256を保存する。同じ内容の再送は**最初のHTTPステータス・本文・ETag**を返し、Idempotency-Replayed: trueを付ける。後から商品を更新していても現在版と入れ替えない。再送の照合は現在版の比較より先に行い、同時確定の競合時も保存済み記録を再読込する。新しい状態はGETで取得する。[If-Match仕様](https://www.rfc-editor.org/rfc/rfc9110.html#name-if-match)

Day 19まではサーバー側の固定操作者local-adminを使用し、クライアントの操作者指定は受け付けない。認証を実装したことにはならない。要求記録の自動TTL・削除は導入せず、保持方針はDay 24で評価する。売上の再送・訂正はDay 8〜10で別途実装する。

## 商品一覧とカーソル

商品UUID昇順。is_active未指定なら有効・無効の両方、指定はtrue/falseのみ。limitは1〜100の整数表記（既定50）、不正値・未知の検索項目・同じパラメーターの複数指定を422にする。

内部Queryを強い整合性で読み、利用可否の条件に合う商品で返却limitを満たすまで進める。残りの枠数だけを読むため、まだ返していない一致商品を継続キーで飛ばさない。空ページでもキーがあれば読む。100回のQueryで完了しなければ503 QUERY_BUDGET_EXCEEDEDを返し、途中結果を200にしない。終端確認のため次ページが空になる場合はある。

カーソルは店舗・資源・利用可否・limit・並び順・継続キーと有効期限に結び付け、HMAC-SHA256で署名する。有効期間は15分、改ざん・期限切れ・別条件・他店舗・再起動前のカーソルは400 INVALID_CURSOR。署名鍵はローカルアプリ生成時に乱数で作り、プロセス内だけに保持する。再起動時は一覧を最初から取得する。AWS配備時の鍵管理・複数プロセス間の共有は未実装。

これは商品一覧に必要な実装で、売上の期間横断カーソルはDay 9。複数ページをまたぐ同時更新のスナップショットは保証しない。HMACは認証やアクセス権の代わりではない。

## 利用できる環境と仕様書

商品APIはAPP_ENV=local/testだけで動作する。awsモードはSDK生成前に503で拒否する。API CLIは引き続き127.0.0.1だけで待ち受ける。認証導入前のローカル開発機能を実AWSへ公開しない。healthはAWS接続・認証情報・テーブルを必要としない。

OpenAPI正本は [openapi.yaml](contracts/openapi.yaml)。Day 7ではinfo/serversの実装範囲の説明だけを更新し、商品スキーマ・15操作の設計を維持した。BearerAuthはDay 19の最終設計で、現段階の認証実装を表さない。自動OpenAPI JSONやSwagger UIは引き続き無効。

各操作とコマンドは [DAY7_COMMANDS.md](DAY7_COMMANDS.md)、テスト項目・実績・残課題は [DAY7_REVIEW.md](DAY7_REVIEW.md)。公式資料は2026-10-30に確認した。
