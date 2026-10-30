# Day 4：動作確認コマンドの読み方

Day 4で使う5つのコマンドを、実行順に説明する。実行結果とレビュー項目は [DAY4_REVIEW.md](DAY4_REVIEW.md)、確認する設計は [DATA_MODEL.md](DATA_MODEL.md) と [API_CONTRACT.md](API_CONTRACT.md) を参照する。

確認日：2026-10-30。対象はプロジェクトのuv 0.13.6とMiniStack 1.5.33。Python・Dockerの準備は [DEVELOPMENT.md](DEVELOPMENT.md)、ローカルAWS環境は [LOCAL_AWS.md](LOCAL_AWS.md) に記載する。

## 実行する場所と、コマンドに共通する書き方

ターミナルの作業ディレクトリを`sales-manager-dashboard/`にする。Docker Desktopも起動しておく。場所は次のコマンドで確認できる。

```sh
pwd
```

表示されたパスの末尾が`sales-manager-dashboard`なら、この資料の相対パスで実行できる。

| 書き方 | 意味 |
| --- | --- |
| `$PWD` | シェルが現在の作業ディレクトリのパスへ置き換える |
| `"$PWD/.cache/uv"` | 現在のフォルダ内の`.cache/uv`を指定する。引用符はパスに空白があっても一つの値として渡すため |
| `UV_CACHE_DIR=... コマンド` | そのコマンドと子プロセスへ、uvのキャッシュ保存先を渡す。シェルへ`export`し続ける書き方ではない |
| `.tools/uv/bin/uv` | プロジェクト内に準備したuvの実行ファイルを直接使う |
| 行末の`\` | 次の行へ同じコマンドを続ける。行末の`\`の後ろに空白を付けない |

`.tools/uv/bin/uv`の代わりに、PATH上に用意した同じバージョンの`uv`も使える。たとえば`uv sync ...`へ置き換える。`UV_CACHE_DIR`の指定はuvのキャッシュに関する設定であり、Python本体やDockerの保存先すべてを変えるものではない。[uvのキャッシュ設定](https://docs.astral.sh/uv/reference/cli/#uv-sync--cache-dir)

## 1. 検証用の依存関係をそろえる

```sh
UV_CACHE_DIR="$PWD/.cache/uv" .tools/uv/bin/uv sync \
  --project infra/local-aws --group contracts --locked
```

全体としては「ローカルAWS検証用の仮想環境を、契約検証のライブラリも含めて、保存済みのロックに合わせる」という意味になる。

| 部分 | 意味 |
| --- | --- |
| `sync` | 必要な依存パッケージを仮想環境へ導入・同期する |
| `--project infra/local-aws` | このフォルダのPythonプロジェクトを対象にする |
| `--group contracts` | 通常のSDK依存に加え、contractsグループのjsonschema・openapi-spec-validator・PyYAMLも導入する |
| `--locked` | ロックが不足・不整合なら失敗させる。uv.lockを自動更新して先へ進まない |

依存定義は [pyproject.toml](../infra/local-aws/pyproject.toml)、固定した解決結果は [uv.lock](../infra/local-aws/uv.lock) にある。ダウンロードが必要な初回実行ではネットワークを使う。[uv syncの公式説明](https://docs.astral.sh/uv/reference/cli/#uv-sync)

### 仮想環境を手動で作らなくてよい理由

uvが`infra/local-aws/.venv/`を作成・再利用する。アプリ本体の`apps/api/.venv/`とは別の環境である。続くコマンドも`uv run --project infra/local-aws`を使うため、手動の`python -m venv`や`source .../activate`は不要になる。必要なPython本体が見つからない場合のuvによる自動取得は、パッケージ用仮想環境とは別の処理となる。[uvのプロジェクト実行](https://docs.astral.sh/uv/concepts/projects/run/)

## 2. API契約・入力条件・金額の設計例を確認する

```sh
UV_CACHE_DIR="$PWD/.cache/uv" .tools/uv/bin/uv run \
  --project infra/local-aws --group contracts --locked \
  python scripts/verify_day04_contract.py
```

| 部分 | 意味 |
| --- | --- |
| `run` | 対象プロジェクトの依存環境を確認し、その環境で後続のプログラムを実行する |
| `--project`・`--group`・`--locked` | 1と同じ環境・依存グループ・ロック条件を使う |
| `python` | uvが選んだ仮想環境のPythonで実行する |
| `scripts/verify_day04_contract.py` | このリポジトリの契約検証スクリプトを指定する |

`--project`はPythonプロジェクトを選ぶ指定で、作業ディレクトリを移動する指定ではない。そのため、`scripts/...`は引き続きリポジトリのルートから解釈される。[uv runの公式説明](https://docs.astral.sh/uv/reference/cli/#uv-run)

契約ファイルの正本は [openapi.yaml](contracts/openapi.yaml)。スクリプトはPyYAMLの`safe_load`で読み込んでから検証するため、実行コマンドはそのままでよい。初回や依存更新後は1の`sync --locked`を実行する。

[スクリプト](../scripts/verify_day04_contract.py)は次の6グループを確認する。

1. 商品・売上・履歴・エラーなどの応答例がスキーマに合うこと。
2. OpenAPI文書、15操作、更新時の要求ヘッダーが定義されていること。
3. 小数・bool・不正数量・明細数超過・空理由などを拒否すること。
4. 商品スナップショット、訂正条件、期間、JSTの日付境界が設計に合うこと。
5. 訂正・取消後の金額、商品フィルター、CSVの明細金額が一致すること。
6. 50明細のトランザクション項目数・サイズが設計上の予算内であること。

成功時の目印は次の表示。時間の値は環境により変わる。

```text
Ran 6 tests in ...s

OK
```

続いて容量の設計例も表示される。CSVの確認はメモリ上で書き出して再読込するもので、このコマンドによってダウンロード用CSVファイルを保存するわけではない。MiniStackの起動はこの検証には不要。

## 3. MiniStackを起動して準備完了を待つ

```sh
docker compose --env-file /dev/null -f compose.yaml up -d --wait --wait-timeout 90
```

| 部分 | 意味 |
| --- | --- |
| `docker compose` | Composeファイルに定義したコンテナ構成を操作する |
| `--env-file /dev/null` | 空のファイルを環境変数ファイルとして指定し、既定の`.env`の自動読込を避ける |
| `-f compose.yaml` | ルートのMiniStack用Composeファイルを使う |
| `up` | 必要なコンテナ・ネットワークなどを作成して起動する |
| `-d` | バックグラウンドで動かす。ターミナルは次の操作に使える |
| `--wait` | サービスがrunningまたはhealthyになるまで待つ。この構成にはヘルスチェックがあるためhealthyを待つ |
| `--wait-timeout 90` | 準備完了を待つ上限を90秒にする。90秒後にサービスを自動停止する指定ではない |

`--wait`自体もバックグラウンド実行を含むため、ここでの`-d`は明示のための指定である。[Compose upの公式説明](https://docs.docker.com/reference/cli/docker/compose/up/)

`--env-file`はシェルに既に存在する環境変数をすべて消す機能ではない。この[Composeファイル](../compose.yaml)はMiniStackを使い、実AWSの資格情報やLocalStack Auth Tokenを必要としない。[Composeの環境変数ファイル](https://docs.docker.com/compose/how-tos/environment-variables/variable-interpolation/#substitute-with---env-file)

接続口は`127.0.0.1:4566`、保存領域は名前付きボリューム。初回は固定イメージの取得も必要になる場合がある。healthyは起動確認であり、続く保存・訂正の検証結果とは分けて扱う。

## 4. MiniStack上で保存・訂正・競合を確認する

```sh
UV_CACHE_DIR="$PWD/.cache/uv" .tools/uv/bin/uv run \
  --project infra/local-aws --group contracts --locked \
  python scripts/verify_day04_dynamodb.py
```

2と同じPython環境で、実行するスクリプトだけを[保存検証用](../scripts/verify_day04_dynamodb.py)へ変えている。処理の流れは次のとおり。

1. 接続先を`http://127.0.0.1:4566`に固定し、ダミー資格情報で接続する。
2. `day04-design-`で始まる一意名の検証用テーブルを作る。
3. 架空の商品・売上で登録、訂正、取消、検索、履歴、重複要求、古い版の拒否を確認する。
4. 異なる50商品の54アクション登録・55アクション別日訂正も試す。
5. 最後に作成した検証用テーブルを削除する。

認証設定を分離する[接続ヘルパー](../scripts/verify_local_aws.py)を使うため、この検証で個人のAWS設定や実資格情報は使わない。

成功時は`checks`に10項目が並び、末尾に次のフィールドが表示される。

```json
{
  "check_count": 10,
  "temporary_table_deleted": true
}
```

上のJSONは確認するフィールドの抜粋。途中の検証失敗はエラーとして終了し、finallyでテーブル削除を試みる。プロセスを強制終了した場合は後片付けが実行されない可能性がある。

時計は架空データ用に2027-01-05へ固定している。PCの時計を変更しない。検証完了後にはテストデータを削除するため、画面から同じデータを参照するための投入コマンドではない。

## 5. MiniStackを停止して後片付けする

```sh
docker compose --env-file /dev/null -f compose.yaml down
```

起動時と同じCompose構成を指定し、`down`でそのコンテナと専用ネットワークを停止・削除する。名前付きボリュームと取得済みイメージは通常の`down`では残る。Pythonの仮想環境やuvキャッシュも別の保存領域なので残る。[Compose downの公式説明](https://docs.docker.com/reference/cli/docker/compose/down/)

`--volumes`を追加すると名前付きボリュームも削除対象になるため、通常の動作確認後はこのオプションを付けない。4で作った一時テーブルの削除と、5のコンテナ停止は別の後片付けである。

## どこに変更が残るか

| 場所 | 主な変化 |
| --- | --- |
| `infra/local-aws/.venv/` | 検証用のPython環境を作成・同期する |
| `.cache/uv/` | パッケージなどのキャッシュを作成・再利用する |
| Dockerの管理領域 | イメージ・名前付きボリュームが残る。コンテナ・専用ネットワークはdownで削除する |
| MiniStackの一時テーブル | スクリプトが作成し、終了処理で削除する |

各コマンドはPATHやシェル起動設定を書き換えない。ただし、パッケージ導入やDocker起動によるローカルのファイル・リソース作成は行う。Python本体の準備場所はDay 2の手順を参照する。

HTTP API・ブラウザー画面の操作、実AWSの互換性、負荷性能は、ここでのコマンド検証とは別に後続Dayで確認する。
