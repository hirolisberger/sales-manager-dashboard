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
| `2261125`（初回 `eec7aeb`） | 初期ドキュメント・除外設定・GitHub連携手順を登録。作者名・noreply修正後のID |
| `725a856`（初回 `4492b07`） | プロジェクト名と配置をsales-manager-dashboardへ変更。作者名・noreply修正後のID |

今回のDay 0資料と記事は `feature/day00` で作成し、レビュー待ちにします。レビュー承認前にmainへマージしません。最新の状態とレビュー対象コミットは [PROGRESS.md](PROGRESS.md) に記録します。

## GitHubと連携する手順

ユーザーが [DF-HW/sales-manager-dashboard](https://github.com/DF-HW/sales-manager-dashboard) を作成し、originの登録とmainの初回pushを完了しました。以下は、その操作の流れを記録したものです。

その後、個人アカウントで開発を継続する方針になりました。個人側のリポジトリは未作成です。既存の接続記録は残し、新しい個人アカウントのURLを推測して設定しません。切り替え手順は [GITHUB_SETUP.md](GITHUB_SETUP.md) にまとめています。

1. 自分のGitHubアカウントで、`sales-manager-dashboard` という空のリポジトリを作成します。公開範囲を選び、README・`.gitignore`・ライセンスの自動追加は選びません。
2. HTTPS用の認証を準備します。認証入力でパスワードを求められた場合はPersonal Access Tokenを使用します。作成方法と権限の設定は [GITHUB_SETUP.md](GITHUB_SETUP.md) にまとめています。
3. プロジェクトルートで次のコマンドを実行します。このプロジェクトではユーザーが実行済みです。

   ```sh
   git remote add origin https://github.com/DF-HW/sales-manager-dashboard.git
   git remote -v
   git push -u origin main
   ```

4. GitHubのmainに初期ファイルが表示されることを確認します。ローカルでは `git branch -vv` でmainと `origin/main` の対応を確認できます。

この流れは [GitHub公式の既存リポジトリ追加手順](https://docs.github.com/en/migrations/importing-source-code/using-the-command-line-to-import-source-code/adding-locally-hosted-code-to-github) に基づきます。

初回pushでは、パスワード入力を求められずに成功しました。Gitの認証設定は `osxkeychain` であり、macOSのキーチェーンに保存済みの認証情報が使われた可能性が高いと考えられます。認証情報の内容や、どのトークンが使われたかは確認していません。初回push時はmainと `origin/main` が `4492b07` で一致し、追跡設定が完了していました。

その後、選択した個人アカウントのnoreplyを使用し、作者名も `hirolisberger` に固定する方針になりました。作者名の変更時点の10コミットを修正し、現在のローカルmainは `725a856` です。GitHubへの反映はまだ行っておらず、`origin/main` は旧IDのままです。各コミットのファイル内容・メッセージ・日時と、作業ファイル9件が修正前後で保たれていることを確認しました。

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
| 既存接続先へのmainの初回push | ユーザーが実施済み。作者修正後のmainのGitHub反映は未実施 |
| 個人アカウントでの公開用リポジトリ | 未作成。URL確定後にoriginと記事リンクを更新する |
| 端数処理・計上日・訂正取消の詳細決定 | Day 1で実施 |
| Node.js・Pythonなどの採用バージョンと環境構築 | Day 2で整備。現在のインストール状況は未確認 |
| LocalStackの環境構築 | Day 3で実施 |

GitHubの接続完了はDay 1開始の必須条件にはしません。必要な準備資料の確認・承認と、Day 1の開始指示を受けてから進めます。

## 検証とレビューで確認してほしいこと

資料の検証結果とレビュー対象コミットは [PROGRESS.md](PROGRESS.md) を参照してください。GitHub連携はユーザーの成功ログとローカルのGit設定・参照から確認済みです。認証情報の内容と使用トークンの識別、ブラウザー上の表示は未確認です。アプリケーションのテスト環境はDay 2以降に整備します。

レビューでは、プロジェクトの配置、業務前提、25記事の進め方、GitHub接続手順、記事の匿名化、個人側への接続先切り替えとURL追記の扱いを確認してください。Day 0はレビュー待ちで停止し、Day 1には自動的に進みません。
