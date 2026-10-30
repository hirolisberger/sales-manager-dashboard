# sales-manager-dashboard / 売上管理システム

小規模店舗の商品別売上を管理する `sales-manager-dashboard` を、Next.js、Python、ローカルAWS環境、AWSで開発します。Day 3ではMiniStackを採用する構成とし、LocalStackとの比較結果も記録します。開発過程はQiita Advent Calendar 2026向けの本編25記事と、追加のDay 0準備編として記録します。

Day 0〜4は承認・mainへのマージ済みです。Day 2は [PR #1](https://github.com/hirolisberger/sales-manager-dashboard/pull/1)、Day 3は [PR #2](https://github.com/hirolisberger/sales-manager-dashboard/pull/2)、Day 4は [PR #3](https://github.com/hirolisberger/sales-manager-dashboard/pull/3) でマージしました。完成版はday02〜day04タグで参照できます。

**Day 5のFastAPI基盤・設定読込・共通エラー・要求ID・テストと記事は、2026-10-30にレビュー承認済みです。** 承認対象は`6f52323`で、PR作成・mainマージ・day05タグ作成を残しています。 [API基盤の仕様](docs/API_FOUNDATION.md)、[起動・確認コマンド](docs/DAY5_COMMANDS.md)、[検証・レビュー記録](docs/DAY5_REVIEW.md)、[記事](qiita/day05-fastapi-foundation-and-tests.md) を参照してください。現在の実装済みパスはGET /healthです。商品・売上APIと保存処理は後続Dayで実装します。ローカルAWSの起動は [手順と比較](docs/LOCAL_AWS.md) に記載しています。

## 目指す機能

- 小規模店舗の商品別売上管理
- 売上の登録・一覧・詳細・訂正・取消
- 商品などのマスタ管理
- 期間や商品による検索、日別・月別・商品別の集計、ダッシュボード
- 日別・月別の表示切り替えと、過去の指定日・月の売上の参照
- CSVによる出力と取り込み
- 認証・アクセス制御、入力検証、監視
- ローカルAWSエミュレーターでの検証とAWSへのデプロイ

## ユーザーから確認済みの業務前提

| 項目 | 方針 |
| --- | --- |
| 利用場面 | 小規模店舗の商品別売上管理 |
| 利用者・権限 | 管理者のみ。将来アカウントを分けても同じ画面を使用する想定。利用者ごとの画面や複数ロールは初期要件に含めない |
| 完成の基準 | 商品登録、売上登録、日別・月別の売上集計、CSV出力を一連の操作として行える |
| 期間の切り替え | 日別・月別の表示・集計単位を切り替え、過去の指定日・月の売上を参照できる |
| 金額 | 日本円の税込整数円・整数数量。小数の入力は拒否し、税抜額・消費税額の内訳は初期範囲に含めない |
| 計上日と変更 | 日本時間の取引日を手入力でき、過去日の登録・訂正・取消を認めて変更履歴を残す。訂正後の最新版を集計し、取消済みは除外する |
| Day 1のレビュー対象 | 商品・売上の項目、入力上限、未来日の扱い、期間・集計・CSV・履歴・構成の設計案 |

税込整数円・整数数量と、計上日・訂正取消・集計の方針はDay 1の追加質問で確認済みです。今回の金額範囲では丸め処理は発生しません。その他の詳細も [REQUIREMENTS.md](docs/REQUIREMENTS.md) の設計案としてレビュー承認を受けました。CSV取り込みはDay 18の追加機能とし、会計・税務申告や多通貨対応は初期範囲に含めません。

## 技術方針

| 領域 | 方針 |
| --- | --- |
| フロントエンド | Next.js / TypeScript |
| バックエンド | Python 3.14.9 / FastAPI 0.162.0 / Uvicorn 0.54.0。Day 5の基盤はレビュー待ち |
| ローカルAWS環境 | MiniStack 1.5.33。Docker Compose・digest固定・名前付きボリューム。LocalStack 2026.8.2の比較条件は手順書に記録 |
| AWS | DynamoDBによるデータ管理、S3によるCSV保存、Lambda / API GatewayによるAPI、Cognitoによる認証を候補とする |
| フロントエンド配信 | Next.jsのレンダリング要件を確定した上でAWSの配信構成を選ぶ |
| インフラ | IaCでローカルとAWS実環境を分離する。Terraformを候補とする |
| 品質管理 | フロントエンド・API・集計のテスト、ローカルAWS連携確認、CI |

候補技術の採否、依存バージョン、エミュレーターで利用する機能の対応範囲は、各Dayで公式資料と動作を確認して決定します。今回、実AWSリソースの作成やAWSへのデプロイは行っていません。

Day 3の追加比較では、Auth Token設定後のLocalStackの起動とDynamoDB・S3の検証も成功しました。Cognitoは今回の無料ライセンス対象外という応答だったため、無料でCognitoまで検証する目的に対してMiniStackを推奨します。詳細は [比較結果](docs/LOCAL_AWS.md) を参照してください。

## 現在のファイル構成

```text
AdventCalendar_2026/
└── sales-manager-dashboard/ # プロジェクト・Gitのルート
    ├── .git/                # 既存の履歴を引き継いだGit管理情報
    ├── .gitignore           # 生成物・秘密情報の除外
    ├── .nvmrc               # Node.jsの採用版
    ├── compose.yaml         # MiniStackの起動・状態保持
    ├── AGENTS.md            # 開発・記事・レビュー・Git・公開のルール
    ├── README.md            # 概要と進め方
    ├── apps/
    │   ├── web/             # Next.js・npmロック・設定見本・起動確認ページ
    │   └── api/             # Pythonパッケージ・uvロック・設定見本
    ├── infra/local-aws/     # 検証専用SDK・ロックとLocalStack比較用Compose
    ├── scripts/             # ローカルAWS検証と接続境界のテスト
    ├── docs/
    │   ├── ARTICLE_PLAN.md  # 本編25記事とDay 0の計画
    │   ├── DAY0_SETUP.md    # 開発準備の記録
    │   ├── REQUIREMENTS.md  # Day 1の業務要件と完成条件
    │   ├── ARCHITECTURE.md  # Day 1の構成図と設計判断
    │   ├── DAY1_REVIEW.md   # Day 1の設計例と検証記録
    │   ├── DEVELOPMENT.md   # Day 2の環境導入・起動・検証手順
    │   ├── DAY2_REVIEW.md   # Day 2の実行結果とレビュー項目
    │   ├── LOCAL_AWS.md     # Day 3の比較・起動・停止・環境分離
    │   ├── DAY3_REVIEW.md   # Day 3の検証結果とレビュー項目
    │   └── ROADMAP.md       # Day 1〜25の開発・記事計画
    └── qiita/
        ├── day00-project-setup-and-github.md # Qiita向けDay 0記事
        ├── day01-requirements-and-architecture.md # Qiita向けDay 1記事
        ├── day02-nextjs-python-development-environment.md # Qiita向けDay 2記事
        └── day03-ministack-localstack-local-aws.md # Qiita向けDay 3記事
```

`AdventCalendar_2026/` の直下にある `sales-manager-dashboard/` が、プロジェクトとGitのルートです。これまでの成果物と `.git` をすべてこの中に移動しました。今後作成するソースコード、記事、設定、ドキュメントもこの中に配置します。

親の `AdventCalendar_2026/` から作業を始める場合は、次のコマンドで移動します。

```sh
cd sales-manager-dashboard
```

以降のパスは、特記がない限りプロジェクトルートからの相対パスです。開発コマンドとGit操作もプロジェクトルートで実行します。

記事本文は `qiita/` に配置しています。Day 2で `apps/web/`（Next.js）と `apps/api/`（Python）、Day 3で `compose.yaml` と `infra/local-aws/`・`scripts/` を追加しました。ローカルAWSの起動・確認・停止は [LOCAL_AWS.md](docs/LOCAL_AWS.md) に従ってください。IaCは後続Dayで扱います。

`docs/GITHUB_SETUP.md` と `docs/PROGRESS.md` はローカル専用資料として保持し、Gitの追跡対象から外します。上の構成図は共有するファイルを示しており、この2ファイルはclone先には含まれません。レビュー・検証の共有情報はREADME、各Dayの確認記録、PRで確認できます。

`qiita/` は投稿前のレビュー、投稿後の修正履歴、各Dayのコードとの対応を確認するため、引き続きGitで管理します。Qiitaへの投稿後もMarkdown原稿を残します。

## Day 0：開発前の準備

準備の記録は [DAY0_SETUP.md](docs/DAY0_SETUP.md)、公開用の本文は [Day 0記事](qiita/day00-project-setup-and-github.md) にまとめています。ユーザーの方針変更により、Day 0もQiita公開を想定して作成します。本編25記事とは別の準備編とし、公開日は未定です。Day 1〜25の公開予定日は維持します。

Day 0の資料と記事は `feature/day00` で作成し、2026-10-28にレビュー承認を受けてローカルmainへマージしました。記事のコマンド例では個人名・メールアドレス・PC名・ローカルパスを仮表記にします。個人アカウント側の公開用リポジトリは作成済みで、記事に確定したURLを記載しています。Day 1はユーザーの開始指示を受けてから着手します。Qiitaへの投稿は別途の明示的な指示が必要です。

## 開発とレビュー

Day 1の成果物は [要件定義](docs/REQUIREMENTS.md)、[全体設計](docs/ARCHITECTURE.md)、[設計確認記録](docs/DAY1_REVIEW.md)、[Qiita記事](qiita/day01-requirements-and-architecture.md) です。`feature/day01` で作成し、2026-10-28のレビュー承認後にmainへマージしました。Day 2は2026-10-29の開始指示を受け、`feature/day02` で [環境構築手順](docs/DEVELOPMENT.md)、[確認記録](docs/DAY2_REVIEW.md)、[記事](qiita/day02-nextjs-python-development-environment.md) とコード・設定を作成しました。

開発は毎日行う必要はなく、ユーザーの都合に合わせて進めます。1回の作業では原則一つのDayを扱い、公開日程とは分けて管理します。

1. ユーザーの開始指示を受けて、次のDayに着手します。
2. 前Dayの承認・マージを反映したmainから `feature/dayNN` を作成します。
3. そのDayのソースコードや設定と、対応する `qiita/dayNN-<topic>.md` を一緒に作成・検証します。
4. 両方が完成し、必要な動作確認を終えたら、featureブランチをGitHubへpushしてmain向けのPRを作成します。開発を「実装完了」、レビューを「レビュー待ち」にし、テスト結果・記事・PRのURLを提示して停止します。
5. 修正指示は同じfeatureブランチでコードと記事の両方へ反映し、検証して同じPRへpushします。
6. ユーザーが対象Dayの「レビューOK」を伝えた場合のみ承認済みにし、GitHub上でPRをmainへマージします。ローカルmainを同期し、マージコミットに `dayNN` の注釈付きタグを付け、タグもpushします。次のDayは開始指示を受けてから着手します。

このPR・タグ運用は、2026-10-29のユーザー指示によりDay 2以降に適用します。featureのpush・PR作成と、レビュー承認後のPRマージ・タグのpushは、この方針に沿って行います。Day 0・Day 1はローカルでマージした実績を保持し、過去Dayのタグ付与は別途の指示を受けて行います。

featureブランチはpush後にGitHubから確認でき、マージ後も原則保持します。Qiita記事では、各Dayの完成版を `day01`、`day02` などのタグで案内します。例えば `day02` 作成・push後の参照先は `https://github.com/hirolisberger/sales-manager-dashboard/tree/day02` です。タグはそのDayまでのコード・設定・記事を含む状態を参照します。共有済みタグは移動・上書きせず、修正時には別タグを付けます。

次のDayへの着手には、実装完了、必要な動作確認の実施、記事Markdownの完成、ユーザーのレビュー承認が必要です。Qiitaへの投稿・予約登録・公開完了は着手条件に含めません。レビュー待ちの間は次のDayへ自動的に進みません。

各Dayの完了報告には、実装内容、変更ファイル、テスト・動作確認結果、記事保存先、レビュー確認項目、未解決事項、次のDayへ進める状態かどうかを記載します。

Gitリポジトリのルートは `sales-manager-dashboard/` です。コミットの作者名とGitHub上の紐づけ先は `hirolisberger` とし、その個人アカウントのnoreplyを使用します。現在の作業ブランチは、main/day04 `eda0c85` から作成した `feature/day05` です。Day 5はレビュー承認済みで、PRは既定どおりブラウザーで作成・マージします。PR・タグの実績は確認記録とローカル台帳に残します。

GitHubの接続先は [hirolisberger/sales-manager-dashboard](https://github.com/hirolisberger/sales-manager-dashboard) です。承認済みのDay 0資料・記事を含むmainの初回pushを完了し、ローカルとGitHub側のコミットID一致を確認しています。個人環境の認証・復旧記録はローカル資料で管理し、公開リポジトリには含めません。

詳しいルールは [AGENTS.md](AGENTS.md)、各Dayの到達点は [ROADMAP.md](docs/ROADMAP.md)、全25記事のタイトル・概要案は [ARTICLE_PLAN.md](docs/ARTICLE_PLAN.md) を参照してください。

## Qiitaへの公開

**本編の公開予定日は2026年12月1日〜12月25日、毎日1記事に固定**します。Day 1は12月1日、Day 25は12月25日です。追加のDay 0は公開日未定として別管理します。日付は日本時間（Asia/Tokyo）で管理し、公開時刻は未設定です。開発・レビューが早く完了しても、予定日前に全体公開しません。

記事はローカルの下書きから作成し、Qiitaを利用する場合も非公開の下書き、または限定共有を基本とします。レビュー承認だけを理由に投稿せず、Qiitaへの投稿・更新・限定共有・予約登録・全体公開は、ユーザーが明示的に許可した範囲でのみ行います。

公開前に記事の内容、URL、公開範囲を確認します。予約登録にはQiita公式のAdvent Calendar予約投稿機能を優先し、利用可否と操作仕様は実行時に確認します。登録成功時は対象日と結果を記録し、失敗・確認不能時は「未登録」と報告します。予約登録だけでは公開済みにしません。

ローカル専用の `docs/PROGRESS.md` では、次の状態を独立して記録します。記事ファイル、Qiita記事URL、検証結果、予約結果、実際の公開日時も管理します。共有が必要な結果は各Dayの確認記録・PRにも残します。

| 項目 | ステータス |
| --- | --- |
| 開発 | 未着手 / 実装中 / 実装完了 |
| レビュー | 未着手 / レビュー待ち / 修正中 / 承認済み |
| 公開 | 未投稿 / 限定共有 / 予約登録済み / 公開済み |

Qiita記事URLは限定共有・予約登録時にも取得後に記録します。公開が遅れても予定日は書き換えず、実際の公開日時と遅延理由を別に残します。

## ローカル開発を始める前に

採用版はNode.js 24.22.2 / npm 11.19.1、Python 3.14.9 / uv 0.13.6です。導入・設定・停止方法は [DEVELOPMENT.md](docs/DEVELOPMENT.md) を参照してください。実行環境を切り替えた上で、プロジェクトルートから実行します。

```sh
npm --prefix apps/web ci
uv sync --project apps/api --locked
npm --prefix apps/web run dev
```

`http://127.0.0.1:3000` で確認用ページを表示します。別のターミナルでPython環境を確認します。

```sh
uv run --project apps/api --locked sales-manager-api
```

Python側は実行メッセージを出して終了します。HTTP APIや設定読込はDay 5で実装します。Docker・LocalStackの起動はDay 3の対象です。

実認証情報は `.env` などのローカル設定や適切な秘密情報管理先に置き、Gitには含めません。共有する設定見本にはダミー値を使います。AWS実環境へのデプロイや課金リソースの作成は、対象と変更内容を確認してから行います。
