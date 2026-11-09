# 【Day 10】売上の訂正・取消を実装する：重複登録と同時更新への対策

シリーズ：**Next.js・Python・AWSで作る売上管理システム**

公開予定：2026年12月10日（日本時間）。開発・レビューとQiitaへの公開は別に管理しています。

前回は[売上検索・詳細・ページング](https://github.com/hirolisberger/sales-manager-dashboard/blob/day09/qiita/day09-sales-search-detail-and-pagination.md)を作りました。今回は登録した売上の数量・計上日を訂正し、理由付きで取り消せるようにします。

## この記事の到達点と前提

- 訂正前後の値・理由・操作者・時刻を履歴に残す
- 古い版からの上書きと、同じ要求の二重処理を防ぐ
- 計上日を変更しても日付別データと詳細を一致させる
- 取消後も明細と金額を残し、履歴をページングで読む

Python 3.14.9・uv 0.13.6・FastAPI 0.162.0・Boto3 1.43.121・MiniStack 1.5.33を使います。依存とロックは前回から変更していません。商品・売上APIは認証前のlocal/test専用です。認証はDay 19、集計はDay 15、操作画面はDay 14で追加するため、今回はcurlとテストで確認します。

リポジトリは[sales-manager-dashboard](https://github.com/hirolisberger/sales-manager-dashboard)。完成版はday10タグで共有する予定です。この記事のレビュー待ち時点ではタグ未作成で、Qiita公開前にリンクを確認します。

全コマンドと各指定の意味は[Day 10の手順書](https://github.com/hirolisberger/sales-manager-dashboard/blob/day10/docs/DAY10_COMMANDS.md)、詳細なルールは[訂正・取消の仕様](https://github.com/hirolisberger/sales-manager-dashboard/blob/day10/docs/SALE_CHANGES.md)、結果は[検証記録](https://github.com/hirolisberger/sales-manager-dashboard/blob/day10/docs/DAY10_REVIEW.md)にまとめます。これらのday10リンクもタグ作成後に有効性を確認します。公式資料の確認日は2026年11月9日です。

## 1. 売上IDを増やさず、版を増やす

登録済みのコーヒー550円×2を1個へ訂正するとき、売上IDを新しくすると二重計上の原因になります。同じ売上IDのversionを増やし、最新版だけを検索・集計の対象にします。

| 操作 | 状態 | 版 | 金額 |
| --- | --- | --- | --- |
| 登録 | confirmed | 1 | 1,100円 |
| 数量2→1へ訂正 | confirmed | 2 | 550円 |
| 取消 | cancelled | 3 | 550円を保持 |

取消は売上を物理削除しません。confirmedの検索から除外し、all/cancelledでは明細と金額を確認できます。取消後の再訂正・再取消・復活は受け付けません。日別・月別の集計APIはまだ作っていないので、今回は検索結果と保存データでこの条件を確認します。

追加するAPIは次の三つです。

| API | 入力・用途 |
| --- | --- |
| PATCH /sales/{sale_id} | 訂正後の計上日・全明細・理由 |
| POST /sales/{sale_id}/cancel | 取消理由 |
| GET /sales/{sale_id}/revisions | 版の昇順で履歴を取得 |

理由は空白だけを除く1〜500文字。単価・数量は従来どおり整数で、合計はAPIで再計算します。訂正で明細を1件だけ変える場合でも、残したい明細をすべて送ります。

## 2. 古い画面からの上書きをIf-Matchで防ぐ

詳細取得のETagが"v1"なら、更新時にIf-Match: "v1"を送ります。別の操作が先に版2へ更新していたら412 VERSION_CONFLICTです。更新前に読んだversionをDynamoDBの書込条件にも使うため、読取直後に競合しても上書きしません。

If-Match不足は428、形式不正は400として扱います。今回のAPIは単一の強いETagだけを受け付けます。条件付き更新の意味は[RFC 9110](https://www.rfc-editor.org/rfc/rfc9110.html#name-if-match)、428は[RFC 6585](https://www.rfc-editor.org/rfc/rfc6585.html#section-3)を参照しました。

If-Matchは「自分が見た版のままか」を確認する条件です。一度成功した要求の再送を見分けるためには、別の情報も必要です。

## 3. 同じ要求の再送は、最初の応答を返す

更新にはUUIDのIdempotency-Keyも必須にします。同じキー・メソッド・URL・正規化した本文・If-Matchなら、初回の応答を返します。処理をやり直して版や履歴を増やしません。本文やIf-Matchを変えたキー再利用は409です。

注意したいのは、再送の応答と最新版が異なる場合です。

1. v1からv2への訂正が成功する。
2. 別の要求で取り消してv3になる。
3. 最初の訂正要求を同じ条件で再送すると、v2の初回応答が戻る。
4. GETで取得すると、現在のcancelled/v3が戻る。

再送の照合は現在版の確認より先に実行します。応答にはIdempotency-Replayed: trueを付けます。登録要求の再送も、後で取り消したからといって201/v1から変えません。

一時的な保存競合は503/Retry-After: 1になり得ます。この場合は同じ要求を再送します。入力を変えて再操作するなら、最新版をGETして新しい要求キーを作ります。

## 4. 取引時の商品名を残す

既存明細にはline_idがあります。同じline_idとproduct_idを送った場合は、商品コード・名称のスナップショットを保持します。マスタが改名・無効化されても、過去の数量や実売単価を訂正できます。

line_idを省略した新規明細、商品IDの差し替え、refresh_product_snapshot=trueの場合だけ、現在有効な商品から名称を取得します。読取時の商品版と有効状態も保存時に確認します。マスタの標準単価で、明示的に送った実売単価を上書きしません。

他の売上の明細IDや重複した明細IDは422です。削除した明細は最新版から外れますが、訂正前の履歴には残ります。

## 5. 日付別コピーと履歴をまとめて保存する

Day 9の検索は日付別の売上コピーを読みます。CURRENTだけを更新すると、一覧では昨日の1,100円、詳細では一昨日の550円という不一致が起きます。

日付を変更する訂正では、次の項目を一つのトランザクションで処理します。

```text
CURRENT                旧versionを条件に更新
REV#0000000002         変更前後・理由・操作者・日時を追加
REQUEST#... / KEY#...   初回応答を保存
旧DAY#... / SALE#...    旧versionを条件に削除
新DAY#... / SALE#...    未存在を条件に追加
必要な商品             versionと有効状態を確認
```

同じ日付ならコピーの条件付き更新だけです。最大50種類の商品を含む日付変更で55アクションになります。どれかの条件が失敗したら、履歴や日付コピーだけが保存される状態にしません。[DynamoDB公式資料](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/transaction-apis.html)の全成功・全失敗の仕組みを使います。MiniStackで確認した結果と、実AWSでの検証は分けます。

## 6. curlで登録→訂正→取消→再送を試す

作業ディレクトリはsales-manager-dashboard/です。[手順書](https://github.com/hirolisberger/sales-manager-dashboard/blob/day10/docs/DAY10_COMMANDS.md)の手順1〜4でMiniStack・テーブル・APIを起動し、確認専用の商品と昨日の売上を登録します。

手順5では、登録応答からline_idを取り出し、数量1・計上日をさらに1日前にしたJSONを作ります。そのファイルと要求キーを使う送信部分は次のとおりです。同じターミナルで手順5のPythonを実行し、手順4のday10_sale_idを保持していることが前提です。

```sh
curl -sS -D .cache/day10-corrected-headers.txt \
  -o .cache/day10-corrected.json -w '%{http_code}\n' \
  -X PATCH "http://127.0.0.1:8000/sales/$day10_sale_id" \
  -H 'Content-Type: application/json' \
  -H 'If-Match: "v1"' \
  -H "Idempotency-Key: $(cat .cache/day10-patch-key.txt)" \
  --data-binary @.cache/day10-patch-body.json
```

200・version=2・550円になります。続いて手順6で"v2"を条件に取り消すと、cancelled/v3です。手順7では履歴のnext_cursorを応答から取り出し、created→corrected→cancelledを順に確認できます。

履歴はlimit=1で取得しても、最後の項目の後に空の終端ページを返す場合があります。itemsの件数ではなくnext_cursor=nullで終了します。カーソルの文字列を手で作らず、条件を変えずに直前の応答を使います。15分経過やAPI再起動後は一覧を取り直します。

手順8で同じ訂正要求を再送すると、初回のv2・Idempotency-Replayed: true。手順9の新しい要求キーでは、古い版条件が412、現在版を指定しても取消済みなので409になります。

## 今回の確認結果

```sh
UV_CACHE_DIR="$PWD/.cache/uv" .tools/uv/bin/uv run \
  --project apps/api --locked pytest apps/api/tests -q
UV_CACHE_DIR="$PWD/.cache/uv" .tools/uv/bin/uv run \
  --project apps/api --locked python scripts/verify_day10_sale_changes.py
```

単体・HTTPテスト330件（追加78件）と、実MiniStack12項目に成功しました。同時に同じ版へ書き込む試験では、別キーなら一方の更新だけが成功し、同じキーなら初回と再送の扱いになり、履歴が一度だけ増えることを確認しました。一時的な保存競合は同じ要求を再試行する検証です。

実Uvicornとcurlでも手順書3〜9の7ブロックを専用テーブル・専用ポートで実行し、金額・日付・履歴・再送と最新版の違いを照合しました。検証用テーブルとAPIは片付け、既存データを変更していません。

実AWSのIAM・配備・1MiBのページ境界・応答サイズ・性能・複数プロセスの鍵共有は未検証です。強い整合性の読取でも、複数ページ全体を同一時点に固定する仕組みは実装していません。ローカルで動いたことを、そのままAWS配備の完了とは扱いません。

## まとめと次回

訂正では最新版と履歴・日付別コピーを一括更新し、取消では金額を残して対象状態を変えました。版条件で上書きを防ぎ、要求キーで再送を見分けることで、それぞれの失敗に応じた操作を説明できるようになりました。

Day 10の実装とこの記事はレビュー待ちです。承認・PRマージ・day10タグの登録後、別途の開始指示を受けてDay 11の画面とAPI接続へ進みます。Qiitaへの投稿は別に管理します。
