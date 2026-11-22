# Day 9：売上検索・詳細・ページング

2026-11-08作成・レビュー承認済み。[PR #8](https://github.com/hirolisberger/sales-manager-dashboard/pull/8)でmainへマージし、day09タグはee5e451を参照する。手順は[DAY9_COMMANDS.md](DAY9_COMMANDS.md)、結果・完了情報は[DAY9_REVIEW.md](DAY9_REVIEW.md)。以下はDay 9時点の実装範囲で、Day 10の追加は[訂正・取消仕様](SALE_CHANGES.md)を参照する。

## 追加したAPI

| API | 結果 |
| --- | --- |
| GET /sales | 期間・商品・状態で絞った一覧。200、items / next_cursor |
| GET /sales/{sale_id} | 現在版と全明細。200、Sale、ETag |

商品・売上APIは引き続きlocal/test専用。認証前のawsモードはSDK生成前に503。操作者local-adminは開発用で、本人認証ではない。実AWSには接続していない。売上訂正・取消・履歴参照はDay 10、画面は後続Dayで実装する。

## 検索条件

| パラメーター | 条件 |
| --- | --- |
| start_date / end_date | 必須、実在するYYYY-MM-DD、開始・終了日を含む1〜366日 |
| product_id | 任意、単一UUID。指定した商品が存在しなくても一覧は空 |
| status | all（既定）/ confirmed / cancelled |
| limit | 1〜100、既定50。返す売上件数の上限 |
| cursor | 任意、直前のnext_cursor文字列をそのまま指定 |

未来日を含む検索期間は許可する。登録時の「JST本日以前」とは別の条件。逆順・不正日・翌日を表現できない9999-12-31は422 VALIDATION_ERROR、367日以上は422 PERIOD_TOO_LONG。不正UUID・status・limit、未知・重複パラメーターも422。数値の小数・先頭ゼロ・trueなどをlimitへ変換しない。

検索結果は**計上日降順、同日内は売上UUID降順**。登録日時順ではない。日付ごとのDAY#パーティションをScanIndexForward=False・ConsistentRead=TrueのQueryで読む。ScanやGSIへの切り替えはしない。

## 一覧の金額と詳細

一覧にはlinesを含めず、SaleSummaryを返す。

| 項目 | 意味 |
| --- | --- |
| total_amount_yen | 元の売上全体の合計 |
| matched_amount_yen | 商品条件に一致する明細の合計 |
| matched_quantity | 商品条件に一致する明細の数量合計 |

コーヒー550円×2と紅茶330円×1の売上を紅茶で検索すると、total_amount_yen=1430、matched_amount_yen=330、matched_quantity=1。商品を指定しなければ全明細が対象。状態条件は売上全体に適用する。

詳細はSALE#{UUID}/CURRENTを強い整合性のGetItemで読み、保存された商品名・コード・単価と全明細を返す。商品マスタを改名・値上げ・無効化しても過去の明細は変わらない。存在しない売上や別店舗のIDは404 SALE_NOT_FOUND。不正なID形式は422。

## 継続位置と読取予算

カーソルは「次に読む日付」と「その日の最後に消費したキー」を保持する。日付の末尾なら次の日付へ移し、開始日まで読み終えたらnext_cursor=null。期間下端の0001-01-01でも日付の減算がオーバーフローしないよう終端を先に判定する。

内部QueryのLimitは、APIが返したい残り件数に合わせる。商品・状態で外れた売上や、空のItemsに継続キーがある場合も読み進める。返さなかった一致売上を読み飛ばす先読みは行わない。返す件数へ到達しても未読データが条件に合うかは未確定のため、最終的に空ページを返す場合がある。next_cursor=nullまで続ける。

1要求あたりの内部Queryは最大1,000回。空の366日なら366回で終えられる。フィルターで大量に外れる場合などに上限へ達したら503 QUERY_BUDGET_EXCEEDEDとRetry-After: 1を返し、途中までのitemsを200で返さない。件数制限はRCU・応答時間・課金額の上限保証ではない。

## 署名と境界

Day 7の署名処理をSignedCursorsへ共通化し、商品のPK/SK検証と売上のday/last_key検証を分けた。商品カーソルの形式・期限は維持する。商品と売上は別のアプリ内鍵を使う。

売上カーソルは店舗・資源・期間・商品・状態・並び順・limitに結び付け、15分の有効期限とHMAC-SHA256を検証する。状態内の読取日付・店舗・日付パーティション・売上キー形式も確認する。改ざん・期限切れ・条件変更・API再起動後は400 INVALID_CURSOR。空文字や仮の文字列も無効なので、手順書は応答から自動で取り出す例にした。

HMACは暗号化や本人認証ではない。カーソルは複数ページを一つのデータ時点に固定しない。ページ間に登録・訂正・日付移動があれば、最初からの再検索と同じ集合になる保証はない。今回の重複・欠落の検証は同時更新がないデータで行い、追加後のページがスナップショットではないことも単体テストで確認した。

API仕様書は [openapi.yaml](contracts/openapi.yaml)。Day 9は実装範囲の説明だけを更新し、既存のSale/SaleSummary/SalePageと全15操作の設計は維持した。
