# sales-manager-dashboardと自分のGitHubアカウントとの連携

## 現在の状態

- `AdventCalendar_2026/sales-manager-dashboard/` をプロジェクトとGitのルートとし、mainと既存のコミット履歴を引き継いでいる。
- ローカルのコミットには、すでに設定されているGitの作者名・メールアドレスを使用する。
- GitHubのリモートリポジトリは未設定。リモート作成、アカウント認証、pushはまだ行っていない。
- GitHub CLI（`gh`）は現環境で見つからなかったため、この手順ではブラウザーとGitを使う。
- Day 1の開始時に `feature/day01` を作成する。GitHubの接続はDay 1開始の必須条件ではない。

## 1. GitHubに空のリポジトリを作成する

ブラウザーで自分のGitHubアカウントにログインし、[新規リポジトリ作成画面](https://github.com/new) を開く。

- 所有者は自分のアカウントを指定する。
- リポジトリ名は `sales-manager-dashboard` を使用する。
- Public / Privateは、ソースコードを全体公開するかどうかに合わせて選ぶ。Qiita記事の公開範囲とは別の設定になる。
- README、`.gitignore`、ライセンスの自動追加は選ばず、空のリポジトリを作成する。ローカルにある履歴をそのまま送るためである。

これは今後ユーザーが実施する手順であり、このドキュメントの作成時点でGitHubリポジトリを作成したものではない。[GitHub公式の既存リポジトリ追加手順](https://docs.github.com/en/migrations/importing-source-code/using-the-command-line-to-import-source-code/adding-locally-hosted-code-to-github) に基づく。

## 2. HTTPSでの認証を準備する

すでにGitHub用の認証が設定されている場合は、その方法を利用できる。認証状況はまだ確認していない。

HTTPSでユーザー名とパスワードの入力を求められる場合、ユーザー名にはGitHubのユーザー名、パスワード欄にはPersonal Access Token（PAT）を入力する。GitHubのログインパスワードはGitのHTTPS認証に使用しない。[GitHub公式の認証説明](https://docs.github.com/en/get-started/git-basics/about-remote-repositories) を参照。

PATを使う場合は、[公式のトークン管理手順](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens) に従ってFine-grained tokenを作成する。自分を所有者に指定し、対象リポジトリを限定して、通常のpushに必要なContentsの読み書き権限と有効期限を設定する。将来、CIの定義など操作対象が変わる場合は、その時点で必要な権限を確認する。

トークンは認証入力欄で使用し、チャット・記事・設定ファイル・リモートURLには書き込まない。GitHub CLIやGit Credential Managerを導入して認証する方法も、同じ公式手順から確認できる。

## 3. ローカルのGitに接続先を登録してpushする

作業ディレクトリは `AdventCalendar_2026/sales-manager-dashboard/`。次の `YOUR_GITHUB_USERNAME` を自分のGitHubユーザー名に置き換える。GitHubの作成画面に表示されたHTTPS URLを使ってもよい。

```sh
git remote add origin https://github.com/YOUR_GITHUB_USERNAME/sales-manager-dashboard.git
git remote -v
git push -u origin main
```

`origin` は接続先に付ける名前である。`remote add` はローカルの接続設定を追加し、`push` はコミットをGitHubへ送る。[GitHub公式手順](https://docs.github.com/en/migrations/importing-source-code/using-the-command-line-to-import-source-code/adding-locally-hosted-code-to-github) に従い、push後はGitHub上にファイルとmainブランチが表示されることを確認する。

このコマンド例は未実行。Codexがリモート作成やpushを行う場合は、ユーザーが許可した対象・公開範囲・操作に従う。実際に接続した後、`docs/PROGRESS.md` のGitリポジトリ欄に結果を記録する。

## 4. コミットの作者とGitHubアカウントの紐づけ

Gitの作者名・メールアドレスと、GitHubへのログイン認証は別の設定である。現在の設定はプロジェクトルートで確認できる。

```sh
git config user.name
git config user.email
```

GitHubはコミットのメールアドレスを使って作者をアカウントに紐づける。GitHubのアカウントに登録・確認したメールアドレス、またはGitHubが提供する自分のnoreplyアドレスを使う。設定を変更した場合は以降のコミットに適用され、過去のコミットは自動で変わらない。[GitHub公式のコミットメール設定](https://docs.github.com/en/account-and-profile/how-tos/email-preferences/setting-your-commit-email-address) を参照。

既存の作者設定がGitHubアカウントに登録されているかは未確認であり、今回グローバル設定や過去の履歴は変更しない。
