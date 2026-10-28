# Day 0：売上管理システムの開発準備とGitHub連携

## Day 0の位置づけ

Day 0は、Day 1に入る前に行った準備と、自分のGitHubアカウントに接続する手順・実行結果をまとめた資料です。ユーザーの方針変更により、**Day 0もQiita公開を想定した記事を作成**します。公開本文は [Day 0記事](../qiita/day00-project-setup-and-github.md) に置き、本編25記事とは別の準備編とします。公開日は未定で、Day 1〜25の番号と公開予定日はそのまま維持します。

今回は準備資料と公開用の記事本文を作成します。アプリケーションの実装、Day 1の設計資料や記事本文の作成は、Day 1の開始指示を受けてから行います。

## 作るシステムと確認済みの前提

プロジェクト名・リポジトリ名は **sales-manager-dashboard** です。Next.js、Python、LocalStack、AWSを使い、小規模店舗の商品別売上を管理します。

| 項目 | 確認済みの内容 |
| --- | --- |
| 利用者 | 管理者のみ。将来アカウントを分けても画面は共通 |
| 完成の基準 | 商品登録、売上登録、集計、CSV出力を一連の操作で行える |
| 売上の参照 | 日別・月別の表示・集計を切り替え、過去の指定日・月も参照できる |
| 金額 | 日本円の税込金額 |
| Day 1で決めること | 端数処理の方法・単位、計上日、訂正・取消の扱い |

CSV取り込みは既存のDay 18の計画に残しています。詳しい対象範囲は [README.md](../README.md) を参照してください。

## 準備したファイルと配置

すべての成果物とGit管理情報は、`AdventCalendar_2026/sales-manager-dashboard/` に置きます。作業コマンドも、このプロジェクトルートで実行します。

```text
AdventCalendar_2026/
└── sales-manager-dashboard/
    ├── .git/
    ├── .gitignore
    ├── AGENTS.md
    ├── README.md
    ├── docs/
    │   ├── ARTICLE_PLAN.md
    │   ├── DAY0_SETUP.md
    │   ├── GITHUB_SETUP.md
    │   ├── PROGRESS.md
    │   └── ROADMAP.md
    └── qiita/
        └── day00-project-setup-and-github.md
```

| ファイル | 役割 |
| --- | --- |
| [AGENTS.md](../AGENTS.md) | 開発・記事・レビュー・Git・公開のルール |
| [README.md](../README.md) | プロジェクト概要と業務前提 |
| [ROADMAP.md](ROADMAP.md) | 全25Dayの成果物と確認項目 |
| [ARTICLE_PLAN.md](ARTICLE_PLAN.md) | 全25記事のタイトル・概要案 |
| [PROGRESS.md](PROGRESS.md) | 開発・レビュー・公開の実績 |
| [GITHUB_SETUP.md](GITHUB_SETUP.md) | GitHubの作成・認証・接続・pushの手順 |
| [.gitignore](../.gitignore) | 認証情報、環境変数、生成物などの除外 |
| [Day 0記事](../qiita/day00-project-setup-and-github.md) | 個人情報を仮表記にしたQiita公開用の本文 |

## Gitの準備状況

Gitの初期化と、プロジェクト名・配置の変更は完了しています。既存のコミット履歴を引き継いでいます。

| コミット | 内容 |
| --- | --- |
| `2261125` | 初期ドキュメント・除外設定・GitHub連携手順を登録 |
| `725a856` | プロジェクト名と配置をsales-manager-dashboardへ変更 |

今回のDay 0資料と記事は `feature/day00` で作成し、レビュー待ちにします。レビュー承認前にmainへマージしません。最新の状態とレビュー対象コミットは [PROGRESS.md](PROGRESS.md) に記録します。

## GitHubと連携する手順

個人アカウントの [hirolisberger/sales-manager-dashboard](https://github.com/hirolisberger/sales-manager-dashboard) を使用します。リポジトリの作成、originの設定、読み取り確認は完了しており、初回pushは未実施です。以下は、このリポジトリに初めて接続する場合の手順です。

1. 自分のGitHubアカウントで、`sales-manager-dashboard` という空のリポジトリを作成します。公開範囲を選び、README・`.gitignore`・ライセンスの自動追加は選びません。
2. HTTPS用の認証を準備します。認証入力でパスワードを求められた場合はPersonal Access Tokenを使用します。作成方法と権限の設定は [GITHUB_SETUP.md](GITHUB_SETUP.md) にまとめています。
3. プロジェクトルートでoriginを登録し、接続先を確認します。このプロジェクトではoriginを設定済みのため、`remote add` の再実行は不要です。

   ```sh
   git remote add origin https://github.com/hirolisberger/sales-manager-dashboard.git
   git remote -v
   git ls-remote origin
   ```

4. mainの初回pushを行います。これは今後実施する操作で、現時点では未実施です。

   ```sh
   git push -u origin main
   ```

5. push後にGitHubのmainに初期ファイルが表示されることと、`git branch -vv` でmainの追跡先が `origin/main` になっていることを確認します。

この流れは [GitHub公式の既存リポジトリ追加手順](https://docs.github.com/en/migrations/importing-source-code/using-the-command-line-to-import-source-code/adding-locally-hosted-code-to-github) に基づきます。

読み取り確認では、認証なしの `ls-remote` とfetchが正常終了し、参照がないことを確認しました。まだコミットを送信していないため、GitHub側にmainはありません。mainの追跡設定はoriginのmainですが、`origin/main` の参照は初回push後に作成されます。詳しい手順と確認結果は [GITHUB_SETUP.md](GITHUB_SETUP.md) にまとめています。

作者名は `hirolisberger` に固定し、個人アカウントの確認済みnoreplyを使用しています。ローカルmainは `725a856` です。認証helperには `osxkeychain` が設定されていますが、初回push時に使用する認証情報や書き込み権限は未検証です。

現在の作業ブランチは `feature/day00` です。上記のpushが送るのはmainであり、レビュー待ちのDay 0資料は含まれません。Day 0を承認してmainへマージした後、mainを再度pushすると資料も反映されます。レビュー用にDay 0のブランチを共有する場合は、対象ブランチを明示して別途pushします。

GitHub操作をCodexに依頼する場合も、対象リポジトリと許可された操作に従います。この準備資料の作成だけを理由に外部へ送信しません。実行した結果は [PROGRESS.md](PROGRESS.md) に追記します。

## 完了した準備と残っている作業

| 項目 | 現在の状態 |
| --- | --- |
| プロジェクト名・配置の統一 | 完了 |
| 開発・記事・Git・レビュー・公開のルール | 作成済み |
| 25Dayの計画と記事タイトル・概要案 | 作成済み |
| 確認済みの業務前提の記録 | 完了 |
| Gitの初期化とローカルの作者修正 | 完了。作者名を固定する変更時点の10コミットを `hirolisberger` と確認済みnoreplyへ統一 |
| Day 0資料・公開用記事・GitHub連携手順 | 作成済み・レビュー待ち。実際のQiita投稿は未実施 |
| 個人アカウントでの公開用リポジトリ | 作成済み。originの設定、読み取り確認、記事リンクの記載を完了 |
| mainの初回push | 未実施。送信後にGitHub上のファイルと追跡先を確認する |
| 端数処理・計上日・訂正取消の詳細決定 | Day 1で実施 |
| Node.js・Pythonなどの採用バージョンと環境構築 | Day 2で整備。現在のインストール状況は未確認 |
| LocalStackの環境構築 | Day 3で実施 |

GitHubの接続完了はDay 1開始の必須条件にはしません。必要な準備資料の確認・承認と、Day 1の開始指示を受けてから進めます。

## 検証とレビューで確認してほしいこと

資料の検証結果とレビュー対象コミットは [PROGRESS.md](PROGRESS.md) を参照してください。originの設定とGitHubへの読み取り接続を確認済みです。書き込み権限、認証情報の内容と使用トークンの識別、ブラウザー上の表示は未確認です。アプリケーションのテスト環境はDay 2以降に整備します。

レビューでは、プロジェクトの配置、業務前提、25記事の進め方、個人アカウントへの初期接続手順、記事の匿名化、リポジトリリンクを確認してください。Day 0はレビュー待ちで停止し、Day 1には自動的に進みません。
