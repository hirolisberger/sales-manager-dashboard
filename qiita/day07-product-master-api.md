# 【Day 07】商品マスタAPIを作る：登録・更新・無効化と入力検証

シリーズ：**Next.js・Python・AWSで作る売上管理システム**

公開予定：2026年12月7日（日本時間）。開発・レビューとQiita公開は別に管理しています。

## はじめに

[Day 6](https://github.com/hirolisberger/sales-manager-dashboard/blob/day06/qiita/day06-ministack-persistence-and-seed-data.md)では、MiniStackのDynamoDBへ読み書きする保存層と、初期データ用のCLIを作りました。今回はその保存層を使い、商品をHTTPで登録・取得・更新できるようにします。

**実装するのは商品登録・一覧・詳細・更新と、is_activeによる無効化です。** 商品の管理画面は後続Dayで作るため、今回はcurlやブラウザーのJSON表示で確認します。

## この記事の到達点

- 商品コード・名称・税込標準単価を登録し、不正値を拒否する
- 無効化しても商品本体とコード予約を残す
- 古い版での更新と、同じ要求の二重登録を防ぐ
- 利用可否の絞り込みと、継続キーを使った一覧取得を確認する

リポジトリは [sales-manager-dashboard](https://github.com/hirolisberger/sales-manager-dashboard) です。Day 7はレビュー待ちで、完成版の[`day07`タグ](https://github.com/hirolisberger/sales-manager-dashboard/tree/day07)は承認・mainマージ後に作成します。以下のday07文書リンクもタグ作成後に参照可能になります。

確認日：2026-10-30。macOS ARM64、Python 3.14.9、uv 0.13.6、MiniStack 1.5.33で検証しました。Day 5〜6の固定依存を使い、今回ライブラリの更新・追加はしていません。

## 1. 商品APIの責務を分ける

追加した操作は四つです。

| メソッドとパス | 用途・成功応答 |
| --- | --- |
| POST /products | 登録。201と登録商品 |
| GET /products | 一覧。200とitems / next_cursor |
| GET /products/{product_id} | 詳細。200と商品 |
| PATCH /products/{product_id} | 名称・単価・利用可否の更新。200と更新商品 |

入力の型は`product_models.py`、商品の処理と保存計画は`products.py`、HTTPやヘッダーの処理は`product_routes.py`へ分けました。SDKを呼ぶ同期ルートはFastAPIに実行を任せ、依存のyield / finallyでリクエストごとのクライアントを閉じます。[FastAPI公式](https://fastapi.tiangolo.com/tutorial/dependencies/dependencies-with-yield/)

API起動やhealthではテーブルを作成しません。Day 6のinitを明示的に実行して保存先を用意します。

## 2. 入力を丸めたり変換したりしない

商品登録の本文は次の形です。

```json
{
  "code": "COFFEE",
  "name": "コーヒー",
  "default_unit_price_yen": 550
}
```

商品コードは大文字英数字から始まる1〜32文字で、後続は大文字英数字・ハイフン・アンダースコアです。名称は空白だけを除く1〜100文字、税込標準単価は0〜9,999,999円の整数にします。

Pydanticのstrictなモデルを使い、`550.0`、`"550"`、`true`を単価550や1へ変換しません。小数を四捨五入する処理もありません。未知フィールドを拒否し、商品ID・版・操作者・日時はクライアントから指定させません。[Pydantic公式](https://docs.pydantic.dev/latest/concepts/strict_mode/)

PATCHはname・default_unit_price_yen・is_activeのうち1項目以上です。空の本文・null・変更不可のcodeも422にします。単価だけ、または利用可否だけの更新ができます。

## 3. 無効化してもコードを解放しない

商品の削除はDELETEではなく、次の更新で行います。

```json
{"is_active": false}
```

無効商品も詳細と無効商品一覧で参照でき、同じ商品をtrueへ戻すこともできます。コード予約は残すため、無効化した商品のコードを別の商品へ登録すると409 PRODUCT_CODE_CONFLICTです。

商品マスタの価格・名称を更新しても、別の売上レコードを書き換える処理は行いません。取引時のスナップショットを保持した売上を実際に登録・訂正する動作は、Day 8以降で確認します。

## 4. 読んだ版を条件に更新する

登録時はversion=1、応答のETagは`"v1"`です。PATCHには、詳細取得で受け取ったETagをIf-Matchへ渡します。次はHTTP要求の例です。IDと要求キーは架空の値です。

```http
PATCH /products/00000000-0000-4000-8000-000000000001
Content-Type: application/json
If-Match: "v1"
Idempotency-Key: 00000000-0000-4000-8000-000000000701

{"name":"コーヒー改","default_unit_price_yen":600}
```

成功するとversion=2・ETag=`"v2"`になります。旧版の条件は、読んだ後の比較だけでなくDynamoDBの書込条件にも入れます。二つの更新が同じ版を読んでも、古くなった側を412 VERSION_CONFLICTで拒否します。[If-Matchの仕様](https://www.rfc-editor.org/rfc/rfc9110.html#name-if-match)

If-Match未指定は428、弱いETag・ワイルドカード・複数指定・上限外の版は400です。成功した更新は、値が同じでも版を増やします。版が上限に達した場合は更新を拒否します。

## 5. 再送には最初の成功応答を返す

POSTとPATCHにはIdempotency-Keyを必須にしました。同じUUID・操作・本文・If-Matchの再送では、商品をもう一度保存せず、最初の成功応答を返します。

| 保存操作 | 同じトランザクションで確定する項目 |
| --- | --- |
| 登録 | 商品本体、商品コード予約、最初の成功応答 |
| 更新 | 旧版条件付き商品本体、最初の成功応答 |

商品だけ保存され、要求記録が保存されない状態を避けます。同時登録で同じコードや要求キーが競合した場合も、複数項目がまとめて成功・失敗する仕組みを使います。[DynamoDB公式](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/transaction-apis.html)

たとえば登録後に商品をversion=3へ更新していても、元の登録を再送すれば、最初の201・version=1・ETag=`"v1"`を返します。Idempotency-Replayedはtrueです。現在の状態が必要ならGETで取得します。

このため、再送の照合を現在版の比較より先に行います。同じキーで別の本文・別操作・別If-Matchを送る場合は409 IDEMPOTENCY_CONFLICTです。売上の訂正・取消の再送は、後続Dayで別途実装します。

## 6. 絞り込みで途中の商品を飛ばさない

一覧は商品UUID昇順で、is_active未指定なら有効・無効の両方を返します。true/falseで絞り込み、limitは1〜100、既定50です。

内部Queryの評価件数と、APIが返す件数は一致しないことがあります。無効商品が途中にある場合は、返却limitを満たすか終端に達するまで続きを読みます。残りの枠数を超えて読み進めないことで、まだ返していない一致商品を飛ばさないようにしました。空ページでも継続キーがあれば読みます。

next_cursorは店舗・条件・limit・並び順・継続位置・有効期限を結び付け、HMAC-SHA256で署名します。検証時は署名を照合し、改ざんや別条件での再利用を400にします。[Pythonのhmac](https://docs.python.org/3/library/hmac.html)

有効期間は15分です。今回はアプリ生成時の乱数鍵をプロセス内に保持するため、API再起動後は最初から取得します。複数プロセスやAWS配備での鍵共有は未実装です。複数ページを一つの時点のスナップショットにする保証もありません。

## 7. 手元で確認する

以下はプロジェクトルートで実行します。uvの配置が違う場合は`.tools/uv/bin/uv`を自身のuvへ置き換えてください。

```sh
UV_CACHE_DIR="$PWD/.cache/uv" .tools/uv/bin/uv sync --project apps/api --locked
docker compose --env-file /dev/null -f compose.yaml up -d --wait

UV_CACHE_DIR="$PWD/.cache/uv" .tools/uv/bin/uv run \
  --project apps/api --locked \
  sales-manager-data --env-file apps/api/.env.example init

UV_CACHE_DIR="$PWD/.cache/uv" .tools/uv/bin/uv run \
  --project apps/api --locked \
  sales-manager-api --env-file apps/api/.env.example
```

別ターミナルから一覧を取得できます。ブラウザーで同じURLを開いてもJSONを確認できます。

```sh
curl -i 'http://127.0.0.1:8000/products?is_active=true&limit=1'
```

まだ商品を登録していなければitemsは空です。登録・再送・詳細・更新・無効化・古い版の拒否を順に確認するコマンドと、各指定の意味は[DAY7_COMMANDS.md](https://github.com/hirolisberger/sales-manager-dashboard/blob/day07/docs/DAY7_COMMANDS.md)にまとめました。そこで使う商品名・コード・UUIDは確認用です。

自動検証は次の二つです。

```sh
UV_CACHE_DIR="$PWD/.cache/uv" .tools/uv/bin/uv run \
  --project apps/api --locked pytest apps/api/tests -q

UV_CACHE_DIR="$PWD/.cache/uv" .tools/uv/bin/uv run \
  --project apps/api --locked python scripts/verify_day07_products.py
```

単体テストは141件成功、実際のMiniStackとの結合検証は12項目成功でした。結合検証のHTTP部分はTestClientで処理し、DBには実際に接続します。毎回一意名のテーブルを作り、終了時に削除するため、手元の業務テーブルは変更しません。

別途、実Uvicornとcurlで9項目を確認し、手順書の登録から古い版の拒否までのコマンドも専用テーブルで照合しました。同じコードの同時登録は1件のみ、同じ要求キーの同時送信は同じ商品を返し、同じ版からの同時更新は一方だけが成功しました。

## つまずきと今回の制限

更新後に同じ要求キーを使いながらIf-Matchだけ最新に変えると、別内容として409になります。再送は同じ要求のまま、新しい操作は新しいキーと最新ETagで送ります。また、無効化してもコード予約を残すため、同じコードで別商品を作り直す操作はできません。

認証はまだ実装していません。local/testモードだけを許可し、awsモードではSDK生成前に商品APIを503で拒否します。固定操作者local-adminは開発用で、認証済みの本人を表すものではありません。実AWS・IAM・性能・複数プロセスの鍵管理は未検証です。

## まとめと次回

Day 7では、商品APIと厳格な入力検証を作り、無効化・版条件・最初の成功応答の再送まで確認しました。Day 7はレビュー待ちで、承認・mainマージ・開始指示を受けてからDay 8の売上登録APIへ進みます。

仕様は[PRODUCT_API.md](https://github.com/hirolisberger/sales-manager-dashboard/blob/day07/docs/PRODUCT_API.md)、テスト内容・結果は[DAY7_REVIEW.md](https://github.com/hirolisberger/sales-manager-dashboard/blob/day07/docs/DAY7_REVIEW.md)を参照してください。Qiitaへの投稿・予約・公開は開発と別に管理します。
