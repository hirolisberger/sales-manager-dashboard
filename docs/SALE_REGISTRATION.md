# Day 8：売上登録APIと金額計算

2026-11-02作成。Day 7の承認・[PR #6](https://github.com/hirolisberger/sales-manager-dashboard/pull/6)マージ・[day07タグ](https://github.com/hirolisberger/sales-manager-dashboard/tree/day07)を確認し、main `3768214`から着手。実装範囲はlocal/testの`POST /sales`。手順は [DAY8_COMMANDS.md](DAY8_COMMANDS.md)、結果は [DAY8_REVIEW.md](DAY8_REVIEW.md)。

## 入出力と金額

本文は`YYYY-MM-DD`のsale_dateと1〜50件のlines。明細はproduct_id、unit_price_yen、quantityだけを受け付ける。未知フィールド、合計・商品名・操作者・状態・版・明細IDのクライアント指定を拒否する。

| 項目 | ルール |
| --- | --- |
| 税込単価 | 厳密な整数0〜9,999,999円 |
| 数量 | 厳密な整数1〜9,999 |
| 明細金額 | 取引時の税込単価×数量 |
| 売上合計 | 明細金額の合計、9,999,999,999円以下 |
| 計上日 | 実在する日付、日本時間の本日以前。過去日を許可 |
| 商品 | 現在の店舗に存在する有効商品 |

float・bool・数値文字列・nullを整数へ変換しない。税抜額・税額内訳・丸め処理は設けない。同じ商品を複数明細に指定でき、明細は入力順に1〜50の番号と新しいUUIDを持つ。標準価格とは異なる実売単価を指定できる。商品コード・名称は登録時のマスタから保存する。

計上日の比較はサーバーのタイムゾーン付き時計をAsia/Tokyoへ変換して行う。作成・更新・操作日時は同じ時計からUTCで保存する。OSの日付やクライアント送信の操作時刻には依存しない。IANAタイムゾーンデータが必要で、今回はmacOS ARM64で確認した。

成功時は201、Sale、`ETag: "v1"`、`Idempotency-Replayed: false`。初期状態はconfirmed・version=1・currency=JPY。商品マスタ変更後も登録済み明細は変えない。現在の売上詳細・一覧・訂正・取消・履歴参照HTTP APIは未実装で、後続Dayで追加する。

## 原子的な保存と競合

[保存設計](DATA_MODEL.md)のキーを使い、次の4項目と、異なる商品ごとのConditionCheckを同じTransactWriteItemsへ渡す。

| 保存先 | 内容 |
| --- | --- |
| SALE#{UUID} / CURRENT | 明細を含む売上全体 |
| 同じPK / REV#0000000001 | created、固定操作者、理由null、before=null、after=売上全体 |
| DAY#{計上日} / SALE#{UUID} | 最新版と同じ売上全体の日付別コピー |
| REQUEST#{操作者} / KEY#{要求UUID} | 要求ハッシュ・最初の201本文・ETag |

店舗プレフィックスはサーバー設定で確定する。商品には強い整合性のGetItemを使い、保存時には読み取ったversionとis_active=trueを条件確認する。同一商品の確認は1回にまとめる。50明細・50商品なら54アクション。Day 6の256KiB/項目・3MiB/要求・55アクションの保守的なガードをそのまま使う。

商品が読取後に変更されたら、全書込を失敗させて商品を再読込する。現在も有効だが版が変わっていれば409 PRODUCT_CHANGED、無効化なら409 PRODUCT_INACTIVE、消失なら404 PRODUCT_NOT_FOUND。その他の保存競合・障害は503とRetry-After: 1。自動的に新しい商品名へ差し替えて登録しない。

## 再送

Idempotency-KeyはDay 7と同じ単一UUID形式で必須。店舗・サーバー固定操作者local-admin内で商品APIともキー空間を共有する。別の操作には新しいキーを使う。

POST・正規化した/sales・検証後の本文・If-Matchなしをハッシュ化する。配列の順序も要求内容に含める。同じキー・同じ内容なら最初のSaleと201・v1・Idempotency-Replayed: trueを返す。キーだけ再利用して日付・単価・数量などを変更したら409 IDEMPOTENCY_CONFLICT。

再送判定を現在の商品状態・未来日判定より先に行うため、登録後の商品改名・無効化やAPIアプリ再作成後も最初の応答を返せる。未成功の入力エラーは記録しない。同時要求が既に確定した場合は記録を再読込して返す。まだ処理中なら503の可能性があり、同じキー・同じ本文で再試行する。要求記録を自動削除するTTLは設けない。

## 範囲とエラー

商品・売上APIはawsモードでSDK生成前に503を返す。認証はDay 19に実装予定で、固定操作者は本人認証ではない。実AWSには接続・配備していない。

| HTTP | 主な理由 |
| --- | --- |
| 400 | 不正JSON、欠落・不正・重複した要求キー |
| 404 | PRODUCT_NOT_FOUND |
| 409 | PRODUCT_INACTIVE / PRODUCT_CHANGED / IDEMPOTENCY_CONFLICT |
| 422 | VALIDATION_ERROR / FUTURE_SALE_DATE / AMOUNT_LIMIT_EXCEEDED |
| 503 | 保存障害・未確定の競合・awsモード拒否。Retry-After: 1 |

エラーは共通形式で、入力値・SDK内部情報を応答へ含めない。API仕様書の正本は [openapi.yaml](contracts/openapi.yaml)。Day 8は実装範囲の説明だけを更新し、SaleCreate/Sale/Revisionの設計スキーマを変更していない。最終設計のBearerAuthと、現在の認証実装を区別する。
