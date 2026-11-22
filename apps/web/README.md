# 売上管理のNext.js画面

Day 11では共通レイアウト・ナビゲーション・商品3件の参照・API接続確認と、読込中/空結果/通信失敗/更新を実装した。商品編集・売上入力・集計・認証の画面は後続Day。

プロジェクトルートから、Node.js 24.22.2を選択したターミナルで実行する。

```sh
npm --prefix apps/web ci
API_BASE_URL=http://127.0.0.1:8000 npm --prefix apps/web run dev
```

API_BASE_URLはNext.jsサーバー専用で、Day 11はloopbackのHTTPだけを許可する。APIは別ターミナルで起動する。詳細な準備・コマンドの意味は[DAY11_COMMANDS.md](../../docs/DAY11_COMMANDS.md)、責務と表示の仕様は[WEB_FOUNDATION.md](../../docs/WEB_FOUNDATION.md)、検証は[DAY11_REVIEW.md](../../docs/DAY11_REVIEW.md)を参照する。

testはNode標準テスト、lintはBiome、typecheckはtsc、本番build/startもnpm scriptsで実行する。依存バージョンはpackage-lock.jsonで固定する。API呼出しはServer Componentsから行い、ブラウザーへ接続先や秘密情報を公開しない。認証は未実装なのでローカル確認用として扱う。
