# Day 0：売上管理システムの開発準備とGitHub連携

## Day 0の位置づけ

Day 0は、Day 1に入る前に行った準備と、これから自分のGitHubアカウントに接続する手順をまとめた資料です。**Day 0はQiitaへの投稿対象外**とし、Advent Calendarの全25記事には含めません。Day 1〜25の番号と公開予定日はそのまま維持します。

今回作成するのは準備資料です。アプリケーションの実装、Day 1の設計資料や記事本文の作成は、Day 1の開始指示を受けてから行います。

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
    └── docs/
        ├── ARTICLE_PLAN.md
        ├── DAY0_SETUP.md
        ├── GITHUB_SETUP.md
        ├── PROGRESS.md
        └── ROADMAP.md
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

## Gitの準備状況

Gitの初期化と、プロジェクト名・配置の変更は完了しています。既存のコミット履歴を引き継いでいます。

| コミット | 内容 |
| --- | --- |
| `eec7aeb` | 初期ドキュメント・除外設定・GitHub連携手順を登録 |
| `4492b07` | プロジェクト名と配置をsales-manager-dashboardへ変更 |

今回のDay 0資料は `feature/day00` で作成し、レビュー待ちにします。レビュー承認前にmainへマージしません。最新の状態とレビュー対象コミットは [PROGRESS.md](PROGRESS.md) に記録します。

## GitHubと連携する手順

現時点では、GitHubのリモート作成・接続・pushは未実施です。GitHubへのログイン認証も未確認です。以下はこれから実施する手順であり、接続済みという意味ではありません。

1. 自分のGitHubアカウントで、`sales-manager-dashboard` という空のリポジトリを作成します。公開範囲を選び、README・`.gitignore`・ライセンスの自動追加は選びません。
2. HTTPS用の認証を準備します。認証入力でパスワードを求められた場合はPersonal Access Tokenを使用します。作成方法と権限の設定は [GITHUB_SETUP.md](GITHUB_SETUP.md) にまとめています。
3. プロジェクトルートで次のコマンドを実行します。`YOUR_GITHUB_USERNAME` は自分のGitHubユーザー名に置き換えてください。

   ```sh
   git remote add origin https://github.com/YOUR_GITHUB_USERNAME/sales-manager-dashboard.git
   git remote -v
   git push -u origin main
   ```

4. GitHubのmainに初期ファイルが表示されることを確認します。ローカルでは `git branch -vv` でmainと `origin/main` の対応を確認できます。

この流れは [GitHub公式の既存リポジトリ追加手順](https://docs.github.com/en/migrations/importing-source-code/using-the-command-line-to-import-source-code/adding-locally-hosted-code-to-github) に基づきます。

現在の作業ブランチは `feature/day00` です。上記のpushが送るのはmainであり、レビュー待ちのDay 0資料は含まれません。Day 0を承認してmainへマージした後、mainを再度pushすると資料も反映されます。レビュー用にDay 0のブランチを共有する場合は、対象ブランチを明示して別途pushします。

GitHub操作をCodexに依頼する場合も、対象リポジトリと許可された操作に従います。この準備資料の作成だけを理由に外部へ送信しません。実行した結果は [PROGRESS.md](PROGRESS.md) に追記します。

## 完了した準備と残っている作業

| 項目 | 現在の状態 |
| --- | --- |
| プロジェクト名・配置の統一 | 完了 |
| 開発・記事・Git・レビュー・公開のルール | 作成済み |
| 25Dayの計画と記事タイトル・概要案 | 作成済み |
| 確認済みの業務前提の記録 | 完了 |
| Gitの初期化、main、既存コミットの維持 | 完了 |
| Day 0資料とGitHub連携手順 | 作成済み・レビュー待ち |
| GitHubリポジトリ作成・接続・push | 未実施。手順を実行するときに対応 |
| 端数処理・計上日・訂正取消の詳細決定 | Day 1で実施 |
| Node.js・Pythonなどの採用バージョンと環境構築 | Day 2で整備。現在のインストール状況は未確認 |
| LocalStackの環境構築 | Day 3で実施 |

GitHubの接続完了はDay 1開始の必須条件にはしません。必要な準備資料の確認・承認と、Day 1の開始指示を受けてから進めます。

## 検証とレビューで確認してほしいこと

資料の検証結果とレビュー対象コミットは [PROGRESS.md](PROGRESS.md) を参照してください。GitHubへの実際の認証・pushは未検証です。アプリケーションのテスト環境はDay 2以降に整備します。

レビューでは、プロジェクトの配置、業務前提、25記事の進め方、GitHub接続手順、Day 0がQiita投稿対象外であることを確認してください。Day 0はレビュー待ちで停止し、Day 1には自動的に進みません。
