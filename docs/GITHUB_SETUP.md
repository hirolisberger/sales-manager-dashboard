# sales-manager-dashboardと自分のGitHubアカウントとの連携

## 現在の状態

- `AdventCalendar_2026/sales-manager-dashboard/` をプロジェクトとGitのルートとし、mainと既存のコミット履歴を引き継いでいる。
- コミットの表示名は `DF-HW`、GitHub上の紐づけ先はユーザーが選択した個人アカウント `hirolisberger`。このアカウントの確認済みnoreplyを使用するローカル設定へ変更し、変更時点の既存8コミットのAuthor/Committerも同じnoreplyへ統一した。グローバル設定は変更していない。
- ユーザーが [DF-HW/sales-manager-dashboard](https://github.com/DF-HW/sales-manager-dashboard) を作成し、originの登録とmainの初回pushを完了した。初回push時は `4492b07` で一致していたが、noreply修正後のローカルmainは `1ec4ab1`。`origin/main` は修正前のままで、GitHubへの反映は未実施。
- 今後は個人アカウントで開発を継続する方針。コミットの紐づけ先として個人アカウントは選択済みだが、ユーザーによれば個人側のリポジトリは未作成で、公開先URLは未確定。作者の選択だけを理由にoriginを変更しない。
- GitHub向けのcredential helperは `osxkeychain`。パスワード入力なしでpushが成功し、保存済みの認証情報が使われた可能性が高い。認証情報そのものは読み出しておらず、新しく作成したトークンが使われたかは未確認。
- GitHub CLI（`gh`）は現環境で見つからなかったため、この手順ではブラウザーとGitを使う。
- Day 1の開始時に `feature/day01` を作成する。GitHubの接続はDay 1開始の必須条件ではない。
- 現在の作業ブランチは `feature/day00`。準備記録は [DAY0_SETUP.md](DAY0_SETUP.md)、Qiita向けの公開本文は [Day 0記事](../qiita/day00-project-setup-and-github.md) にまとめる。Day 0も公開を想定して記事を作成するが、投稿操作は未実施。レビュー承認前にmainへマージしない。

## 個人アカウントで継続するための次の対応

ローカルのコード、未コミットのDay 0記事、既存のGit履歴は引き続き利用できる。対応が必要なのは、公開先と認証・作者情報の確認である。GitHubへのログイン、originの所有者、コミットに記録される作者名・メールアドレスは、それぞれ別の設定として確認する。

1. 個人用のGitHubアカウントにログインし、所有者がそのアカウントであることを確認して、`sales-manager-dashboard` を空のリポジトリとして作成する。README、`.gitignore`、ライセンスの自動追加は選ばない。公開前の確認中はPrivateで用意し、記事から一般の読者に共有する段階でPublicにする方法も選べる。
2. 作者名・メールの公開範囲を決める。通常メールを公開したくない場合は個人アカウントのSettings → Emailsでnoreplyアドレスを確認し、このリポジトリのローカル設定に使用する。既存コミットの作者情報は設定変更だけでは変わらず、新しいリポジトリにも引き継がれる。
3. HTTPS用のPATを使う場合は、Resource ownerとアクセス対象が新しい個人アカウントのリポジトリに合うことを確認する。既存のPATが新しい所有者にも使用できるとは限らない。
4. 下記の `YOUR_PERSONAL_GITHUB_USERNAME` を実際の個人アカウント名に置き換え、プロジェクトルートで接続先を変更する。originは登録済みなので、変更には `set-url` を使用する。

   ```sh
   git remote set-url origin https://github.com/YOUR_PERSONAL_GITHUB_USERNAME/sales-manager-dashboard.git
   git remote -v
   git push -u origin main
   ```

5. `git remote -v` とGitHub上の所有者・ファイルを確認し、結果を `docs/PROGRESS.md` に記録する。macOSのキーチェーンが以前の認証情報を使用する場合があるため、権限エラーが出た場合は接続先と認証アカウントを確認する。

この切り替えは未実施。既存のGitHubリポジトリの削除・移管・公開範囲変更も行っていない。originのURL変更だけでは、既存接続先にある履歴や作者情報は消えない。[GitHub公式のリモート管理手順](https://docs.github.com/en/get-started/git-basics/managing-remote-repositories#changing-a-remote-repositorys-url) と [コミットメール設定](https://docs.github.com/en/account-and-profile/how-tos/email-preferences/setting-your-commit-email-address) に基づく。

以下は、これまでの接続作業の記録と一般的な初期設定手順である。

## 1. GitHubに空のリポジトリを作成する

ブラウザーで自分のGitHubアカウントにログインし、[新規リポジトリ作成画面](https://github.com/new) を開く。

- 所有者は自分のアカウントを指定する。
- リポジトリ名は `sales-manager-dashboard` を使用する。
- Public / Privateは、ソースコードを全体公開するかどうかに合わせて選ぶ。Qiita記事の公開範囲とは別の設定になる。
- README、`.gitignore`、ライセンスの自動追加は選ばず、空のリポジトリを作成する。ローカルにある履歴をそのまま送るためである。

このプロジェクトでは、上記のリポジトリ作成はユーザーが実施済み。手順は [GitHub公式の既存リポジトリ追加手順](https://docs.github.com/en/migrations/importing-source-code/using-the-command-line-to-import-source-code/adding-locally-hosted-code-to-github) に基づく。

## 2. HTTPSでの認証を準備する

すでにGitHub用の認証が設定されている場合は、その方法を利用できる。今回の環境では `osxkeychain` が設定されており、ユーザーの初回pushは認証入力を求められずに成功した。保存済みの認証情報が使われた可能性が高いが、使用されたトークンの識別までは確認していない。

認証情報が保存されている場合は、毎回のパスワード入力が省略されることがある。入力が表示されないことだけではエラーとは判断せず、pushの成功ログと追跡先の設定を確認する。[GitHub公式の認証情報保存の説明](https://docs.github.com/en/get-started/git-basics/caching-your-github-credentials-in-git) を参照。

HTTPSでユーザー名とパスワードの入力を求められる場合、ユーザー名にはGitHubのユーザー名、パスワード欄にはPersonal Access Token（PAT）を入力する。GitHubのログインパスワードはGitのHTTPS認証に使用しない。[GitHub公式の認証説明](https://docs.github.com/en/get-started/git-basics/about-remote-repositories) を参照。

PATを使う場合は、[公式のトークン管理手順](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens) に従ってFine-grained tokenを作成する。自分を所有者に指定し、対象リポジトリを限定して、通常のpushに必要なContentsの読み書き権限と有効期限を設定する。将来、CIの定義など操作対象が変わる場合は、その時点で必要な権限を確認する。

GitHubのSettingsからDeveloper settings、Personal access tokens、Fine-grained tokensへ進み、Generate new tokenを選ぶ。Resource ownerは自分、Repository accessはOnly select repositoriesとして `sales-manager-dashboard` を選び、ContentsにRead and writeを設定する。有効期限を指定し、トークンを作成する。

トークンは認証入力欄で使用し、チャット・記事・設定ファイル・リモートURLには書き込まない。GitHub CLIやGit Credential Managerを導入して認証する方法も、同じ公式手順から確認できる。

## 3. ローカルのGitに接続先を登録してpushする

作業ディレクトリは `AdventCalendar_2026/sales-manager-dashboard/`。このプロジェクトでユーザーが実行したコマンドは次のとおり。originの登録とmainの初回pushは完了しているため、以下は実行済みの操作記録として参照する。

```sh
git remote add origin https://github.com/DF-HW/sales-manager-dashboard.git
git remote -v
git push -u origin main
```

`origin` は接続先に付ける名前である。`remote add` はローカルの接続設定を追加し、`push` はコミットをGitHubへ送る。[GitHub公式手順](https://docs.github.com/en/migrations/importing-source-code/using-the-command-line-to-import-source-code/adding-locally-hosted-code-to-github) に従い、push後はGitHub上にファイルとmainブランチが表示されることを確認する。

現在は `feature/day00` で作業しているが、上記のpushはmainを送信する。Day 0の資料は、レビュー承認とmainへのマージ後に改めてmainをpushすることで反映できる。レビュー用に `feature/day00` をGitHubへ送る操作は、別途対象を明示して行う。

接続後は `git branch -vv` でmainの追跡先が `origin/main` になっていることと、GitHubのmainにファイルが表示されることを確認する。認証、リモート登録、初回pushの結果を `docs/PROGRESS.md` に記録する。

今回の実行者はユーザーであり、Codexからpushは行っていない。接続結果は `docs/PROGRESS.md` に記録済み。Codexが今後リモート操作やpushを行う場合も、ユーザーが許可した対象・公開範囲・操作に従う。

## 4. コミットの作者とGitHubアカウントの紐づけ

Gitの作者名・メールアドレスと、GitHubへのログイン認証は別の設定である。現在の設定はプロジェクトルートで確認できる。

```sh
git config user.name
git config user.email
```

GitHubはコミットのメールアドレスを使って作者をアカウントに紐づける。GitHubのアカウントに登録・確認したメールアドレス、またはGitHubが提供する自分のnoreplyアドレスを使う。設定を変更した場合は以降のコミットに適用され、過去のコミットは自動で変わらない。[GitHub公式のコミットメール設定](https://docs.github.com/en/account-and-profile/how-tos/email-preferences/setting-your-commit-email-address) を参照。

今回はユーザーが提示したメール設定画面のnoreplyを使用し、紐づけ先として個人アカウントを選択済み。表示名とGitHub上の紐づけ先は別に扱う。Gitの作者情報とGitHubへのログイン認証も別の設定であり、作者の修正だけで認証アカウントやoriginのURLは変わらない。

## メールアドレスの非公開設定

GitHubのSettings → Emailsで「Keep my email addresses private」と「Block command line pushes that expose my email」を有効にする。Primary / Backup emailは通知や復旧先の設定として扱う。ブラウザー上のチェック状態はこちらでは確認していない。

GitHub上の設定だけでは、コマンドラインの作者メールや過去のコミットは自動で変わらない。このため、今回はローカル設定と既存8コミットのAuthor/Committerを確認済みnoreplyへ変更した。GitHubへの修正履歴の反映は別途必要となる。[GitHub公式の非公開メール露出防止設定](https://docs.github.com/en/account-and-profile/how-tos/email-preferences/blocking-command-line-pushes-that-expose-your-personal-email-address)

## 公開記事とリポジトリの確認結果

記事の操作例では、個人名・メールアドレス・PC名・ローカルパスを仮表記にする。個人側の公開用リポジトリが未作成のため、記事から既存接続先への実リンクを外し、個人側のURL確定後に追記する。

既存履歴を確認したところ、公開済みmainの2コミットには修正前の個人用作者情報が含まれていた。実際の値は記事に再掲しない。最初にローカルの6コミットを指定の表示名・メールへ変更し、その後のメール非公開化の希望とアカウント選択に従って、作業時点の8コミットをnoreplyへ修正した。各コミットのファイルツリー・メッセージ・日時は同一で、作者情報と、それに伴うコミットID・親IDが変更されている。

修正前の履歴、未コミットの9ファイル、差分、Git設定とindexは `.git/author-fix-20261027-mcr3oekv/` にバックアップ済み。このローカルバックアップには旧作者情報が含まれるが、通常のGitコミット・pushの対象にはならない。

noreplyへの変更直前の8コミットと作業ファイル9件は `.git/noreply-fix-20261027-90ev1a55/` にもバックアップ済み。新規コミットもこのnoreplyを使用し、記事のコード例には実際のアドレスを記載しない。

GitHubのmainを修正するには、公開済みの2コミットを修正後の履歴へ更新する必要がある。リモート反映はまだ行っていない。実行する場合は対象をmainだけに限定し、リモートのmainが確認済みの旧コミットと一致する場合だけ更新する `--force-with-lease` を使う。Day 0のレビュー前の内容はmainへマージしない。
