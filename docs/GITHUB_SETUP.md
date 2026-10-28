# sales-manager-dashboardと自分のGitHubアカウントとの連携

## 現在の状態

- `AdventCalendar_2026/sales-manager-dashboard/` をプロジェクトとGitのルートとし、mainと既存のコミット履歴を引き継いでいる。
- コミットの作者名とGitHub上の紐づけ先は、ユーザーが選択した個人アカウント `hirolisberger` に統一する。この作者名と当該アカウントの確認済みnoreplyをリポジトリのローカル設定に使用し、作者名を固定する変更時点の既存10コミットのAuthor/Committerも統一した。グローバル設定は変更していない。
- 現在のoriginは [hirolisberger/sales-manager-dashboard](https://github.com/hirolisberger/sales-manager-dashboard)。ユーザーが個人アカウント側のリポジトリを作成済みで、2026-10-28の切り替え指示に従い、取得・送信の接続先を変更した。
- 新しい接続先へ認証なしで `ls-remote` と `fetch --prune` を実行し、読み取り成功と参照がない状態を確認した。新しいリポジトリにはまだコミットがなく、初回pushは未実施。ローカルmainは `725a856` のまま維持し、旧接続先の追跡参照だった `origin/main` はpruneで整理した。
- 旧接続先 [DF-HW/sales-manager-dashboard](https://github.com/DF-HW/sales-manager-dashboard) へのmain初回pushはユーザーが実施済みで、当時のmainは `4492b07`。旧リポジトリの内容や公開済み履歴は今回変更していない。
- GitHub向けのcredential helperは `osxkeychain`。パスワード入力なしでpushが成功し、保存済みの認証情報が使われた可能性が高い。認証情報そのものは読み出しておらず、新しく作成したトークンが使われたかは未確認。
- GitHub CLI（`gh`）は現環境で見つからなかったため、この手順ではブラウザーとGitを使う。
- Day 1の開始時に `feature/day01` を作成する。GitHubの接続はDay 1開始の必須条件ではない。
- 現在の作業ブランチは `feature/day00`。準備記録は [DAY0_SETUP.md](DAY0_SETUP.md)、Qiita向けの公開本文は [Day 0記事](../qiita/day00-project-setup-and-github.md) にまとめる。Day 0も公開を想定して記事を作成するが、投稿操作は未実施。レビュー承認前にmainへマージしない。

## 個人アカウントへの切り替え記録と次の対応

ユーザーの切り替え指示を受け、プロジェクトルートで次の操作を実施した。

```sh
git remote set-url origin https://github.com/hirolisberger/sales-manager-dashboard.git
git remote -v
GIT_TERMINAL_PROMPT=0 git -c credential.helper= ls-remote --symref origin HEAD 'refs/heads/*'
GIT_TERMINAL_PROMPT=0 git -c credential.helper= fetch --prune origin
GIT_TERMINAL_PROMPT=0 git -c credential.helper= ls-remote origin
```

変更前の設定と参照は `.git/remote-switch-20261028-nyql7owi/` に保存した。新しい接続先には参照がなく、`fetch --prune` により旧 `origin/main` が整理された。ローカルのmain、作業ブランチ、作者設定、既存ファイルは維持している。

次の操作は新しい接続先へのmainの初回pushで、今回は実行していない。ユーザーからpushの指示を受けた際に、対象と送信内容を確認して実施する。現在は空のリポジトリなので、通常のpushで送信でき、旧リポジトリの作者修正に使うforce pushは不要である。

```sh
git push -u origin main
```

このpushで送るmainには、レビュー待ちのDay 0資料は含まれない。初回push後に `origin/main` が作られ、`git branch -vv` で追跡先を確認できる。新しい接続先への書き込み権限と、保存済み認証情報がその操作に使用できるかは未検証。PATを使う場合はResource ownerと対象リポジトリを確認する。

既存のGitHubリポジトリの削除・移管・公開範囲変更は行っていない。originのURL変更だけでは、旧接続先にある履歴や作者情報は消えない。[GitHub公式のリモート管理手順](https://docs.github.com/en/get-started/git-basics/managing-remote-repositories#changing-a-remote-repositorys-url) と [コミットメール設定](https://docs.github.com/en/account-and-profile/how-tos/email-preferences/setting-your-commit-email-address) に基づく。

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

## 3. 旧接続先への初回push（実施済みの記録）

作業ディレクトリは `AdventCalendar_2026/sales-manager-dashboard/`。ユーザーが旧接続先に対して実行したコマンドは次のとおり。以下は実行済みの操作記録であり、現在のoriginを旧URLに戻す手順ではない。

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

今回はユーザーが提示したメール設定画面のnoreplyを使用し、作者名も `hirolisberger` に固定した。作者名とGitHub上の紐づけ先は別の設定だが、今回は同じ表記を選択している。Gitの作者情報とGitHubへのログイン認証も別の設定であり、作者の修正だけで認証アカウントやoriginのURLは変わらない。

## メールアドレスの非公開設定

GitHubのSettings → Emailsで「Keep my email addresses private」と「Block command line pushes that expose my email」を有効にする。Primary / Backup emailは通知や復旧先の設定として扱う。ブラウザー上のチェック状態はこちらでは確認していない。

GitHub上の設定だけでは、コマンドラインの作者メールや過去のコミットは自動で変わらない。このため、noreplyへの変更時点の既存8コミットを修正し、その後、作者名を固定する変更時点の10コミットも確認した。現在はローカル設定とAuthor/Committerが、選択した作者名・確認済みnoreplyで一致している。GitHubへの修正履歴の反映は別途必要となる。[GitHub公式の非公開メール露出防止設定](https://docs.github.com/en/account-and-profile/how-tos/email-preferences/blocking-command-line-pushes-that-expose-your-personal-email-address)

## 公開記事とリポジトリの確認結果

記事の操作例では、個人名・メールアドレス・PC名・ローカルパスを仮表記にする。個人側のリポジトリの作成と読み取り確認を終えたため、記事のリポジトリリンクを確定した個人側のURLに更新した。

既存履歴を確認したところ、公開済みmainの2コミットには修正前の個人用作者情報が含まれていた。実際の値は記事に再掲しない。最初にローカルの6コミットを指定の表示名・メールへ変更し、その後のメール非公開化の希望とアカウント選択に従って、作業時点の8コミットをnoreplyへ修正した。最新の指示で作者名を `hirolisberger` に固定し、その変更時点の10コミットも同じ名前に統一した。各コミットのファイルツリー・メッセージ・日時は同一で、作者情報と、それに伴うコミットID・親IDが変更されている。

修正前の履歴、未コミットの9ファイル、差分、Git設定とindexは `.git/author-fix-20261027-mcr3oekv/` にバックアップ済み。このローカルバックアップには旧作者情報が含まれるが、通常のGitコミット・pushの対象にはならない。

noreplyへの変更直前の8コミットと作業ファイル9件は `.git/noreply-fix-20261027-90ev1a55/` にもバックアップ済み。新規コミットもこのnoreplyを使用し、記事のコード例には実際のアドレスを記載しない。

作者名の固定直前の10コミットと作業ファイル9件は `.git/author-name-fix-20261027-xgn7450a/` にバックアップ済み。履歴のbundle、ファイルのtar、設定・index・新旧コミット対応を保存した。これらのローカルバックアップも通常のpushには含まれない。

旧接続先のmainに残る作者情報を修正する場合は、旧リポジトリに対する別の操作となる。今回の切り替えでは旧リポジトリを変更していない。今後ユーザーから明示的な指示がある場合に限り、対象と最新の参照を確認して履歴更新を行う。新しい接続先には旧履歴がないため、修正済みローカルmainの初回送信は通常のpushで行える。Day 0のレビュー前の内容はmainへマージしない。
