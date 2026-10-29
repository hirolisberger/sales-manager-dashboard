# sales-manager-dashboardと自分のGitHubアカウントとの連携

## 現在の状態

- `AdventCalendar_2026/sales-manager-dashboard/` をプロジェクトとGitのルートとし、mainと既存のコミット履歴を引き継いでいる。
- コミットの作者名とGitHub上の紐づけ先は、ユーザーが選択した個人アカウント `hirolisberger` に統一する。この作者名と当該アカウントの確認済みnoreplyをリポジトリのローカル設定に使用し、作者名を固定する変更時点の既存10コミットのAuthor/Committerも統一した。グローバル設定は変更していない。
- GitHubの接続先は個人アカウントの [hirolisberger/sales-manager-dashboard](https://github.com/hirolisberger/sales-manager-dashboard)。リポジトリはユーザーが作成済みで、originの取得・送信URLも設定済み。
- mainの初回pushはユーザーが完了した。初回push確認時のローカルmain・`origin/main`・GitHub側mainは `d71bc3e` で一致。承認済みのDay 0資料と記事も送信済み。
- GitHub向けのcredential helperは `osxkeychain`。このリポジトリでは認証ユーザーを `hirolisberger` に固定し、資格情報をリポジトリ単位で分ける設定を使用している。ユーザーの認証後にpush成功を確認済み。認証情報そのものは読み出していない。
- GitHub CLI（`gh`）は現環境で見つからなかったため、この手順ではブラウザーとGitを使う。
- Day 1は `feature/day01` で作業し、レビュー承認後にローカルでmainへマージ・pushした。現在はDay 2の開始指示を受け、`feature/day02` で作業する。
- Day 2以降はfeatureをpushしてGitHubのPRでレビューし、承認後にPRをマージして `dayNN` タグを作成・pushする。Gitによるpushの認証と、GitHubのPR操作に必要な接続・権限は別に確認する。最新の実績は [PROGRESS.md](PROGRESS.md) に記録する。
- 準備記録は [DAY0_SETUP.md](DAY0_SETUP.md)、Qiita向けの公開本文は [Day 0記事](../qiita/day00-project-setup-and-github.md) にまとめる。Day 0は2026-10-28にレビュー承認・ローカルmainへのマージを完了した。Qiitaへの投稿操作は未実施。

以下は、個人アカウントのリポジトリへ初めて接続する場合の手順である。このプロジェクトではリポジトリ作成からmainの初回pushまで実施済み。

## 1. GitHubに空のリポジトリを作成する

ブラウザーで自分のGitHubアカウントにログインし、[新規リポジトリ作成画面](https://github.com/new) を開く。

- 所有者は自分のアカウントを指定する。
- リポジトリ名は `sales-manager-dashboard` を使用する。
- Public / Privateは、ソースコードを全体公開するかどうかに合わせて選ぶ。Qiita記事の公開範囲とは別の設定になる。
- README、`.gitignore`、ライセンスの自動追加は選ばず、空のリポジトリを作成する。ローカルにある履歴をそのまま送るためである。

このプロジェクトでは、上記のリポジトリ作成はユーザーが実施済み。手順は [GitHub公式の既存リポジトリ追加手順](https://docs.github.com/en/migrations/importing-source-code/using-the-command-line-to-import-source-code/adding-locally-hosted-code-to-github) に基づく。

## 2. HTTPSでの認証を準備する

すでにGitHub用の認証が設定されている場合は、その方法を利用できる。今回の環境では `osxkeychain` が設定されており、ユーザーの認証後に初回pushが成功した。保存されたトークンの内容は読み出していない。

認証情報が保存されている場合は、毎回のパスワード入力が省略されることがある。入力が表示されないことだけではエラーとは判断せず、pushの成功ログと追跡先の設定を確認する。[GitHub公式の認証情報保存の説明](https://docs.github.com/en/get-started/git-basics/caching-your-github-credentials-in-git) を参照。

HTTPSでユーザー名とパスワードの入力を求められる場合、ユーザー名にはGitHubのユーザー名、パスワード欄にはPersonal Access Token（PAT）を入力する。GitHubのログインパスワードはGitのHTTPS認証に使用しない。[GitHub公式の認証説明](https://docs.github.com/en/get-started/git-basics/about-remote-repositories) を参照。

PATを使う場合は、[公式のトークン管理手順](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens) に従ってFine-grained tokenを作成する。自分を所有者に指定し、対象リポジトリを限定して、通常のpushに必要なContentsの読み書き権限と有効期限を設定する。将来、CIの定義など操作対象が変わる場合は、その時点で必要な権限を確認する。

GitHubのSettingsからDeveloper settings、Personal access tokens、Fine-grained tokensへ進み、Generate new tokenを選ぶ。Resource ownerは自分、Repository accessはOnly select repositoriesとして `sales-manager-dashboard` を選び、ContentsにRead and writeを設定する。有効期限を指定し、トークンを作成する。

トークンは認証入力欄で使用し、チャット・記事・設定ファイル・リモートURLには書き込まない。GitHub CLIやGit Credential Managerを導入して認証する方法も、同じ公式手順から確認できる。

## 3. originを登録して接続を確認する

作業ディレクトリは `AdventCalendar_2026/sales-manager-dashboard/`。初めて接続する場合は、個人アカウントのリポジトリをoriginとして登録する。このプロジェクトでは登録済みのため、`remote add` の再実行は不要。

```sh
git remote add origin https://github.com/hirolisberger/sales-manager-dashboard.git
git remote -v
git ls-remote origin
```

`origin` は接続先に付ける名前である。`remote add` はローカルの接続設定を追加し、`ls-remote` はGitHub側の参照を確認する。初回push後の読み取り確認では、GitHub側のmainのコミットIDがローカルと一致することを確認した。

## 4. mainを初めてpushする（実施済み）

以下はユーザーが実施済みの操作。空のリポジトリへ通常のpushでmainを送信し、mainの追跡先を設定した。

```sh
git push -u origin main
git branch -vv
```

`push` はコミットをGitHubへ送る。[GitHub公式手順](https://docs.github.com/en/migrations/importing-source-code/using-the-command-line-to-import-source-code/adding-locally-hosted-code-to-github) に従い、push後にGitHubのmainに初期ファイルが表示されることと、mainの追跡先が `origin/main` になっていることを確認する。実行結果は `docs/PROGRESS.md` に記録する。

このpushはmainを送信する。Day 0の資料と記事はレビュー承認後にmainへマージ済みなので、初回pushに含まれる。送信後にGitHubのmainで資料と記事を確認する。

## 5. コミットの作者とGitHubアカウントの紐づけ

Gitの作者名・メールアドレスと、GitHubへのログイン認証は別の設定である。現在の設定はプロジェクトルートで確認できる。

```sh
git config user.name
git config user.email
```

GitHubはコミットのメールアドレスを使って作者をアカウントに紐づける。GitHubのアカウントに登録・確認したメールアドレス、またはGitHubが提供する自分のnoreplyアドレスを使う。設定を変更した場合は以降のコミットに適用され、過去のコミットは自動で変わらない。[GitHub公式のコミットメール設定](https://docs.github.com/en/account-and-profile/how-tos/email-preferences/setting-your-commit-email-address) を参照。

今回はユーザーが提示したメール設定画面のnoreplyを使用し、作者名も `hirolisberger` に固定した。作者名とGitHub上の紐づけ先は別の設定だが、今回は同じ表記を選択している。Gitの作者情報とGitHubへのログイン認証も別の設定であり、作者の修正だけで認証アカウントやoriginのURLは変わらない。

## メールアドレスの非公開設定

GitHubのSettings → Emailsで「Keep my email addresses private」と「Block command line pushes that expose my email」を有効にする。Primary / Backup emailは通知や復旧先の設定として扱う。ブラウザー上のチェック状態はこちらでは確認していない。

GitHub上の設定だけでは、コマンドラインの作者メールや過去のコミットは自動で変わらない。現在はローカル設定と既存コミットのAuthor/Committerが、選択した作者名・確認済みnoreplyで一致している。初回pushでは、この確認済みのローカル履歴を送信する。[GitHub公式の非公開メール露出防止設定](https://docs.github.com/en/account-and-profile/how-tos/email-preferences/blocking-command-line-pushes-that-expose-your-personal-email-address)

## 公開記事とリポジトリの確認結果

記事の操作例では、個人名・メールアドレス・PC名・ローカルパスを仮表記にする。個人側のリポジトリの作成と読み取り確認を終えたため、記事のリポジトリリンクを確定した個人側のURLに更新した。

ローカルのAuthor/Committerは `hirolisberger` と確認済みnoreplyに統一済み。作者名を固定する変更時点の10コミットについて、ファイルツリー・メッセージ・日時が維持されていることを確認した。実際のメールアドレスは記事に再掲しない。

修正前の履歴、未コミットの9ファイル、差分、Git設定とindexは `.git/author-fix-20261027-mcr3oekv/` にバックアップ済み。このローカルバックアップには旧作者情報が含まれるが、通常のGitコミット・pushの対象にはならない。

noreplyへの変更直前の8コミットと作業ファイル9件は `.git/noreply-fix-20261027-90ev1a55/` にもバックアップ済み。新規コミットもこのnoreplyを使用し、記事のコード例には実際のアドレスを記載しない。

作者名の固定直前の10コミットと作業ファイル9件は `.git/author-name-fix-20261027-xgn7450a/` にバックアップ済み。履歴のbundle、ファイルのtar、設定・index・新旧コミット対応を保存した。これらのローカルバックアップも通常のpushには含まれない。

確認済みのローカルmainを通常の初回pushで送信済み。Day 0のレビュー承認とmainへのマージを済ませてから送信している。
