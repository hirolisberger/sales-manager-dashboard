# 【Day 0】Next.js・Python・LocalStack・AWSで売上管理システムを作る前に：GitとGitHubの準備

## はじめに

小規模店舗の商品別売上を管理するシステムを、Next.js、Python、LocalStack、AWSで作ります。商品登録から売上登録、日別・月別の集計、CSV出力までを実装し、開発過程をQiita Advent Calendar 2026向けの全25記事として記録する予定です。

本編に入る前に、Day 0としてプロジェクトの配置、作業ルール、Git、GitHubとの連携を整えました。この記事は本編25記事とは別の準備編です。アプリケーションの実装はDay 1以降に進めます。

公開用のリポジトリは [sales-manager-dashboard](https://github.com/hirolisberger/sales-manager-dashboard) です。個人アカウント側に作成し、接続先を切り替えました。現時点ではまだコミットを送信していません。

コマンドやログ中のユーザー名、メールアドレス、PC名、個人を含む絶対パスは、説明用の仮表記にしています。コマンド例の `YOUR_GITHUB_USERNAME` などは、自分の設定に置き換えて使用してください。

## この記事でできるようになること

- 開発するシステムの前提と、Dayごとの進め方を整理する
- プロジェクトとGitのルートをそろえる
- 認証情報や生成物をコミット対象から除外する
- ローカルのmainをGitHubへ送信する
- トークン作成画面や認証入力で迷った点を確認する

今回確認した環境はmacOS、Git 2.52.0です。Next.js、Pythonのアプリケーション、LocalStack、AWS実環境の構築はまだ行っていません。各ツールの採用バージョンと構成は、対象のDayで確認して決めます。

## 1. 作るものと、今回決める範囲を整理する

まず、システムの大まかな前提を決めました。

| 項目 | 今回の方針 |
| --- | --- |
| 利用場面 | 小規模店舗の商品別売上管理 |
| 利用者 | 管理者のみ。将来アカウントを分けても画面は共通 |
| 主な操作 | 商品登録、売上登録、集計、CSV出力 |
| 売上の表示 | 日別・月別を切り替え、過去の指定日・月も参照する |
| 金額 | 日本円の税込金額 |
| 今後決めること | 端数処理の方法と単位、計上日、訂正・取消のルール |

技術の役割は、Next.jsが画面、PythonがAPI、LocalStackがローカルでのAWSサービス連携の検証、AWSが実環境への配置です。具体的なサービスやAPIフレームワークは、設計と検証を経て決めます。LocalStackで利用する機能の対応範囲も、環境構築時に確認します。

Day 0で要件をすべて確定させるのではなく、ここまでをDay 1の設計に渡す前提として整理しました。

## 2. プロジェクトとGitのルートをそろえる

ローカルでは、Advent Calendar用の親ディレクトリの中にアプリケーションのディレクトリを配置します。Gitリポジトリ名には、システムの内容が分かる `sales-manager-dashboard` を使います。

```text
AdventCalendar_2026/
└── sales-manager-dashboard/  # プロジェクトとGitのルート
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

新しく同じ配置を作る場合は、任意の作業場所で次のように用意します。以降のコマンドは `sales-manager-dashboard/` で実行します。

```sh
mkdir -p AdventCalendar_2026/sales-manager-dashboard
cd AdventCalendar_2026/sales-manager-dashboard
```

今回の作業では、最初に親ディレクトリをGitのルートにしていたため、後から既存の `.git` とファイル一式を子ディレクトリへ移しました。既存の履歴を維持し、現在のGitルートは `sales-manager-dashboard/` になっています。新規に始める読者は、最初からこの場所で初期化すれば移動作業は不要です。

## 3. 開発・記事・レビュー・公開を分けて管理する

作成するドキュメントの役割も決めました。

| ファイル | 管理すること |
| --- | --- |
| `README.md` | プロジェクト概要、業務前提、構成 |
| `AGENTS.md` | 開発・記事作成・Git・レビューのルール |
| `docs/ROADMAP.md` | 全25Dayで作るものと確認項目 |
| `docs/ARTICLE_PLAN.md` | 記事のタイトルと概要 |
| `docs/PROGRESS.md` | 開発・レビュー・公開を分けた進捗 |
| `docs/DAY0_SETUP.md` | 準備作業の記録 |
| `docs/GITHUB_SETUP.md` | GitHub接続手順と確認結果 |
| `qiita/` | 公開する記事のMarkdown |

開発は毎日行う必要はなく、作業できる日に一つのDayを進めます。実装や設定と記事をセットで作り、検証結果を添えてレビューを依頼します。レビューで承認されるまでは次のDayへ進みません。

本編の公開予定日は2026年12月1日〜25日とし、Day番号と日付を対応させます。開発やレビューが早く終わっても、公開予定日前に記事を全体公開しない方針です。

「開発が終わった」「レビューで承認された」「記事を公開した」は、別々に記録します。公開完了は、次のDayの開発を始める条件には含めません。

## 4. 最初のコミットの前に.gitignoreを用意する

Gitで管理するファイルと、ローカルだけに置くファイルを分けます。今回の `.gitignore` には、次のような指定を入れました。以下は抜粋です。

```gitignore
# 環境変数。設定見本にはダミー値だけを入れる
.env
.env.*
!.env.example
!.env.*.example

# アプリケーションの生成物・仮想環境
node_modules/
.next/
.venv/
__pycache__/

# 認証情報・秘密鍵
.aws/
*.pem
*.key
.qiita-config.json
.qiita-config.*.json

# LocalStackのデータ
.localstack/
localstack-data/
infra/localstack/volume/

# Terraformのローカル状態や環境固有の値
.terraform/
*.tfstate
*.tfstate.*
*.tfvars
*.tfvars.json
!*.tfvars.example
!*.tfvars.json.example
```

依存関係を再現するためのロックファイルや、ダミー値だけの設定見本はGitに残します。

`.gitignore` は、すでにコミットした認証情報を履歴から消す仕組みではありません。秘密情報が履歴に入った場合は、認証情報の失効・再発行を先に行い、履歴への対応を検討する必要があります。[GitHub公式の機密データ削除の説明](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/removing-sensitive-data-from-a-repository)

## 5. Gitを初期化し、コミットの作者情報を確認する

以下は、新しく同じ構成を作る場合の手順です。今回のリポジトリはすでに初期化済みで、mainに初期ファイルを登録しています。

```sh
git --version
git init -b main
```

公開するリポジトリでは、コミットの作者名とメールアドレスも確認します。GitHubは、コミットに設定したメールアドレスを使って作者をアカウントに紐づけます。[GitHub公式のコミットメール設定](https://docs.github.com/en/account-and-profile/how-tos/email-preferences/setting-your-commit-email-address)

個人用のメールアドレスを公開したくない場合は、GitHubのSettings → Emailsに表示される、自分の `noreply` アドレスを使用できます。次は、リポジトリごとに設定する例です。仮表記をそのまま使わず、自分の値へ置き換えます。

```sh
git config --local user.name "YOUR_GITHUB_USERNAME"
git config --local user.email "YOUR_GITHUB_NOREPLY_EMAIL"
```

この設定例は、公開向けに手順を整理する際に追加したものです。今回の準備で先に確認しておきたかった点でもあります。設定変更の対象は、以降に作るコミットです。過去のコミットの作者名やメールアドレスは、自動では変わりません。[GitHub公式の説明](https://docs.github.com/en/account-and-profile/how-tos/email-preferences/setting-your-commit-email-address#setting-your-email-address-in-git)

今回も、既存のコミットが意図した作者情報になっていないことが後から分かりました。作者名は個人アカウント名と同じ表記に固定し、メールにはそのアカウントのnoreplyを使う方針にしました。バックアップを作成して作者名の変更時点のローカル10コミットを修正し、ファイル内容・メッセージ・日時が同じであることを確認しました。コミットIDも変わるため、公開済みのGitHubへの反映は別の操作として管理しています。操作例では実際の作者メールやアカウント名を仮表記にしています。

GitHubのメール設定では「Keep my email addresses private」を有効にし、必要に応じて「Block command line pushes that expose my email」も有効にします。これらの設定は、既存コミットを自動で匿名化する機能ではありません。コマンドラインで使うメールには、別途Gitの設定が必要です。[GitHub公式の非公開メール露出防止設定](https://docs.github.com/en/account-and-profile/how-tos/email-preferences/blocking-command-line-pushes-that-expose-your-personal-email-address)

READMEやルール、計画を用意したら、対象ファイルを指定して初期コミットにまとめます。

```sh
git add -- .gitignore AGENTS.md README.md docs/
git diff --cached --check
git diff --cached --stat
git commit -m "chore: initialize project"
```

コミット前には、ファイル一覧だけでなく実際の差分も確認します。`git diff --cached` で、そのコミットに入る内容を確認できます。

## 6. GitHubに空のリポジトリを作る

GitHubにログインし、[新しいリポジトリの作成画面](https://github.com/new) を開きます。

所有者を自分のアカウント、名前を `sales-manager-dashboard` とし、公開範囲を選択します。ローカルに初期コミットがあるため、GitHub側ではREADME、`.gitignore`、ライセンスの自動追加を選ばず、空の状態で作成しました。[GitHub公式の既存リポジトリ追加手順](https://docs.github.com/en/migrations/importing-source-code/using-the-command-line-to-import-source-code/adding-locally-hosted-code-to-github)

### リポジトリ名やURLは公開してよいか

公開を意図したサンプルコードのリポジトリ名やURLは、通常は記事に掲載できます。URLは認証に使う秘密情報ではありません。一方、URLには所有者のアカウント名が含まれるため、記事とGitHubアカウントが結び付くことは認識しておきます。

Publicのリポジトリでは、ソースコードやコミット履歴も公開対象になります。本文のスクリーンショットを匿名化することに加え、リポジトリ内のファイル、過去の履歴、コミットの作者情報も確認します。記事にリンクを張る予定があることだけで、リポジトリの中身が安全になるわけではありません。[GitHub公式の公開範囲の説明](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/managing-repository-settings/setting-repository-visibility)

この記事では、作成済みの公開用リポジトリへのリンクを冒頭に掲載しています。操作例のユーザー名やメールアドレスは仮表記にします。トークン、秘密鍵、実在する顧客・売上データは掲載しません。

## 7. HTTPS認証用のトークンを準備する

GitHubにHTTPSで接続するときは、すでに保存されている認証情報を使用できる場合があります。新しくPersonal Access Token（PAT）を用意する場合は、[GitHub公式のトークン作成手順](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens) に従います。

作成画面は、リポジトリ内ではなく、GitHub右上のプロフィール画像から開くアカウント設定にあります。

**Settings → Developer settings → Personal access tokens → Fine-grained tokens → Generate new token**

今回は、自分が所有する対象リポジトリだけにアクセスする設定にします。

| 項目 | 設定例 |
| --- | --- |
| Token name | `sales-manager-dashboard-local` |
| Expiration | 必要な期限。例として30日 |
| Resource owner | 自分のアカウント |
| Repository access | `Only select repositories` |
| Selected repositories | `sales-manager-dashboard` |
| Contents | `Read and write` |

Contentsを選んだときに、読み書きの設定が見つからず迷いました。権限の種類を追加するメニューを閉じてから、追加されたContents行のアクセス範囲を選ぶ、という別の操作になっていました。日本語表示では「読み取りと書き込み」に相当します。

設定後にGenerate tokenを押し、表示されたトークンを手元で保管します。トークンを記事、チャット、GitのリモートURL、コミットする設定ファイルに貼り付けないようにします。

## 8. originを登録し、mainをpushする

プロジェクトルートで、接続先を登録します。次のURLは操作例なので、`YOUR_GITHUB_USERNAME` を自分のユーザー名へ置き換えます。

```sh
git remote add origin https://github.com/YOUR_GITHUB_USERNAME/sales-manager-dashboard.git
git remote -v
git push -u origin main
```

HTTPS認証で入力を求められた場合、ユーザー名にはGitHubのユーザー名、パスワード欄にはPATを入力します。GitHubのログインパスワードを使う手順ではありません。[GitHub公式のPAT利用方法](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens#using-a-personal-access-token-on-the-command-line)

旧接続先への初回pushは成功しました。以下はそのときの成功ログから、ユーザー名を仮表記にした部分だけを抜粋したものです。後述する個人アカウント側への切り替え後は、まだpushしていません。

```text
To https://github.com/YOUR_GITHUB_USERNAME/sales-manager-dashboard.git
 * [new branch]      main -> main
branch 'main' set up to track 'origin/main'.
```

push後は `git branch -vv` でmainの追跡先が `origin/main` になっていることを確認します。旧接続先への初回push時には、ローカルmainと `origin/main` のコミットが一致することも確認できました。

### 個人アカウントのリポジトリへ接続先を切り替える

ローカルのコードと履歴は、そのまま利用できます。2026年10月28日、個人アカウントに作成済みの空のリポジトリへ、originを切り替えました。以下はその手順を仮表記にしたものです。

```sh
git remote set-url origin https://github.com/YOUR_PERSONAL_GITHUB_USERNAME/sales-manager-dashboard.git
git remote -v
git fetch --prune origin
git ls-remote origin
```

接続先の変更は、既存のリモートURLを書き換える操作です。`fetch --prune` で旧接続先の追跡情報も整理しました。[GitHub公式のリモート管理手順](https://docs.github.com/en/get-started/git-basics/managing-remote-repositories#changing-a-remote-repositorys-url)

認証なしで新しい接続先から読み取れることを確認しました。`ls-remote` は正常終了し、参照は表示されませんでした。まだコミットを送信していないため、新しい接続先にはmainもありません。`git branch -vv` で追跡先が `gone` と表示されることがありますが、初回push後に追跡参照が作られます。読み取り成功だけでは書き込み権限の確認にはなりません。

次は新しい接続先への初回pushです。以下は次に実施するコマンドであり、今回の切り替えでは実行していません。新しい接続先は空のため、通常のpushを使用します。

```sh
git push -u origin main
```

新しいリポジトリにも既存のコミット履歴が送られます。作者名やメールアドレスを公開したくない場合は、送信前に履歴と今後の作者設定を確認します。今後の作者設定だけを変えても、過去の情報は変わりません。

### パスワードを求められなくても、成功していれば正常

今回、push時にパスワード入力が表示されませんでした。確認すると、GitHub向けの認証helperには `osxkeychain` が設定されていました。macOSのキーチェーンに保存されていた認証情報が使われた可能性が高いと考えています。

認証情報が保存されている環境では、毎回の入力が省略されることがあります。どのトークンが使われたかまでは確認していませんが、今回確認できたのはpushの成功とmainの追跡設定です。[GitHub公式の認証情報保存の説明](https://docs.github.com/en/get-started/git-basics/caching-your-github-credentials-in-git)

## 9. Dayごとの作業はfeatureブランチで進める

初期設定をmainにまとめた後、Dayごとの作業は専用ブランチで進めます。Day 0の資料とこの記事は、`feature/day00` で作成しています。

```sh
git switch -c feature/day00
```

作業ブランチで記事を作っていても、`git push origin main` が送るのはmainの内容です。未マージのDay 0記事は、その操作だけではGitHubのmainには反映されません。レビュー承認後にmainへマージし、mainをpushすることで反映します。

次のDayも同様に、前のDayをレビューしてからmainへ反映し、新しいブランチを作ります。公開のタイミングはGitのマージとは分けて管理します。

## 今回確認できたこと

| 確認内容 | 結果 |
| --- | --- |
| プロジェクトの配置 | `sales-manager-dashboard/` をプロジェクトとGitのルートに統一 |
| Gitの履歴 | ファイル内容・メッセージ・日時を保ってローカルの作者情報を修正。GitHubへの修正反映は未実施 |
| GitHubへの接続 | 個人側の作成済みリポジトリへ切り替え、読み取り確認に成功。個人側への初回pushは未実施 |
| mainの追跡先 | 設定は `origin/main`。旧参照はpruneで整理済み、新しい接続先にはmainがまだない |
| 認証入力の省略 | `osxkeychain` の設定を確認。使用トークンの識別は未実施 |
| アプリケーション | 未実装。環境構築と動作確認は今後のDayで実施 |

ローカルのGit管理とGitHubへの接続手順を整え、個人アカウント側への接続先変更を完了しました。新しい接続先へのmainの初回pushと、Day 0記事のレビュー・マージは別の作業として残っています。

## まとめと次回

Day 0では、プロジェクトの配置、開発と記事の進め方、Gitの初期設定、GitHubとの連携を整えました。トークン作成画面の場所、Contentsのアクセス設定、保存済み認証情報による入力の省略も、実際につまずいた点として確認できました。

次回のDay 1では、売上管理システムの要件と全体設計を整理します。税込金額の端数処理、計上日、訂正・取消の扱いを決め、各機能の完成条件を具体化する予定です。
