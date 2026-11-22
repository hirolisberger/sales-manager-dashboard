# Day 10：売上の訂正・取消・履歴参照

実装完了・レビュー待ち。[確認コマンド](DAY10_COMMANDS.md)、[検証記録](DAY10_REVIEW.md)、[OpenAPI正本](contracts/openapi.yaml)を参照する。認証前のlocal/test専用で、awsモードはSDK生成前に503。操作者はサーバー固定のlocal-adminで、認証・権限検証はDay 19。

## HTTPと入力

| 操作 | 入力 | 成功 |
| --- | --- | --- |
| PATCH /sales/{sale_id} | sale_date・lines全体・reason | 200 Sale、ETag、Idempotency-Replayed |
| POST /sales/{sale_id}/cancel | reason | 200 Sale、ETag、Idempotency-Replayed |
| GET /sales/{sale_id}/revisions | 任意のlimit・cursor | 200 RevisionPage |

更新2操作はUUIDのIdempotency-Keyと、取得済みのETagをIf-Matchで送る。If-Matchは二重引用符付きの"v1"形式、版は1〜2,147,483,647。弱いETag・複数指定・*は受け付けない。必須If-Matchなしは428、形式や重複ヘッダーは400、初回要求の版不一致は412。存在しない売上は404。不正UUIDは422。

reasonは空白だけを除く1〜500文字。PATCHは部分的な数量だけの変更ではなく、訂正後の計上日と全明細を送る。価格・数量・日付・合計上限は[登録仕様](SALE_REGISTRATION.md)と同じ。未来日はJST本日で判定。合計はサーバーで再計算する。内容が同じでも新しい要求として受理すると版と履歴を増やす。版上限では409 VERSION_LIMIT_EXCEEDED。

## 明細IDと商品スナップショット

- 既存明細はline_idを指定する。同じ売上の現在版にないIDや重複IDは422。
- line_idを省略すると新しい明細UUIDを発行する。明示的なnullは不可。送らなかった旧明細は最新版から外れるが履歴に残る。配列順にline_noを振り直す。
- 同じline_id・同じproduct_id・refresh_product_snapshot=false（省略時）なら、取引時の商品コード・名称を保持する。現在のマスタが無効・削除済みでも数量や実売単価を訂正できる。
- 新しい明細、商品IDの差し替え、refresh_product_snapshot=trueの場合だけ、現在有効な商品からコード・名称を取得する。欠落は404、無効は409、読取後の版変更は409。
- 商品の税込標準単価を実売単価へ自動転記しない。unit_price_yenは毎回明示的に送る。

同じ商品を複数明細で使っても、マスタ確認は商品ごとに一つ。同じ明細IDで別商品へ変更できるが、有効なマスタと版条件が必要。

## 状態と保存

confirmedだけを訂正・取消できる。訂正はconfirmedのまま版+1。取消は金額・計上日・明細を保ったままcancelledへ変えて版+1。取消後の再訂正・再取消は409 SALE_CANCELLED。古い版条件なら先に412。復活・物理削除は実装しない。

同一トランザクションで以下を保存する。

| 項目 | 条件・動作 |
| --- | --- |
| CURRENT | 読み取った旧versionと一致した場合だけ最新版へ更新 |
| REV#版番号10桁 | 未存在条件でbefore/after・理由・操作者・操作時刻を追加 |
| REQUEST#操作者 / KEY#要求UUID | 未存在条件で初回の200・本文・ETagを保存 |
| 日付別コピー | 同日なら旧version条件で更新。日付変更なら旧コピーを条件付き削除し、新日付へ未存在条件で追加 |
| 必要な商品 | 読取時のversionとis_active=trueを条件確認 |

同日は4+商品数、日付移動は5+商品数で最大55アクション。保存層の1項目256KiB・全体3MiBガードを使う。二つの項目を同じキーへ書かない。どれかの条件が失敗したらCURRENT・履歴・日付・要求記録をまとめて保存しない。日付コピーの欠落や新日付の衝突を自動で修復せず503にする。AWS側の上限・同時実行時の挙動は実AWSで別途検証する。[AWSのトランザクション資料](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/transaction-apis.html)

## 再送と競合

再送記録の照合を現在版・商品状態の検証より先に行う。店舗・操作者・要求キーを共有し、method/path/正規化したbody/If-Matchのハッシュで照合する。同じ要求は初回のstatus・本文・ETagを返し、Idempotency-Replayed=true。訂正・取消後に過去の登録要求を再送しても201/v1を返すため、最新版はGETで確認する。内容やIf-Matchだけ変えたキー再利用も409。

同じ版への別要求が競合した場合、勝った要求だけを保存し、後続は412。保存競合時は要求記録・現在版・商品版を再確認する。まだ勝者の結果が読めない一時的な競合は503/Retry-After: 1になり得る。再試行は同じキー・本文・If-Matchで行う。内容を変更する場合は最新売上を取得し直して、新しい要求キーを使う。

## 履歴のページング

履歴はREV#を強い整合性でQueryし、版の昇順で返す。各項目はsale_id/version/operation/actor_id/occurred_at/reason/before/after。登録時はbeforeとreasonがnull。既存履歴は更新しない。

limitは1〜100・既定50。カーソルは15分、有効な店舗・売上ID・資源・並び順・limitへ結び付け、署名と継続キーを確認する。改ざん・期限切れ・条件変更は400 INVALID_CURSOR。API再起動でも鍵が変わり無効になる。最大100 Queryで1ページを埋め、超過時は部分結果を返さず503 QUERY_BUDGET_EXCEEDED。未知・重複の検索条件は422。

複数ページで同じデータ時点を固定しない。新しい訂正がページ取得中に入ると後続ページに現れ得る。limit=100でもbefore/afterを含む大きな応答になり得る。実AWSの1MiB区切り、応答サイズ・Lambda/API Gatewayの制限と性能、複数プロセスの鍵共有は未検証で、Day 20〜23で確認する。

取消済みは検索のstatus=confirmedから除外し、all/cancelledでは金額を保持する。集計APIはDay 15でconfirmedの最新版だけを加算する。今回、集計APIや画面は追加していない。
