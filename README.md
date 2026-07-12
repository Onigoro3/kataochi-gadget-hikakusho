# Angel部門 完全自動投稿ブログ PoC(型落ちガジェット比較所)

投稿先ブログ: `https://kataochi-gadget-hikakusho.hatenablog.com/`(2026-07-13社長最終決定。
**未開設**。開設は下記「社長への依頼事項チェックリスト」参照)

トピック選択 → Yahoo!ショッピングAPI(商品検索API v3)で型落ち/最新モデルのガジェット
商品データ取得 → 独自スコアリング(買い時判定) → Claude API(Sonnet 5)で記事生成
(アウトライン → 本文 → タイトル/メタ → 自己レビュー) → はてなブログへ**公開状態で**
自動投稿、までを1回の実行で行うパイプラインです。GitHub Actionsで毎日自動実行します。

Dragon部門(`../../app/`、型落ち家電ラボ・楽天API版)の実装を土台に、データソースを
Yahoo!ショッピングAPIへ置き換えて移植した構成です。設計判断の経緯は
`../developer/tasks.md` を参照してください。

## 現在のステータス(2026-07-13時点)

**実装スケルトンのみ完成。実際のAPIキー・ブログ未取得のため、まだ動作しません。**
Yahoo!デベロッパーネットワークのClient ID取得・はてなブログ開設等、社長の手作業が
必要な部分が残っています(下記チェックリスト参照)。それらが揃い次第、ローカルでの
試験実行 → GitHub Actions移行という順で進めます。

`blog_auto_post/yahoo_client.py` はYahoo!ショッピングAPI公式ドキュメントの実物を
未確認の状態(Client ID未取得のため)で、公開情報から推測した構造で実装しています。
Client ID取得後、実際のレスポンスと突き合わせてエンドポイントURL・レスポンスの
フィールド名(`_normalize_item()`内)を検証・修正する必要があります(コード内に
`要検証`コメントを残しています)。

## 構成

```
angel/app/
├── main.py                     # メイン実行スクリプト(1回分のパイプライン)
├── requirements.txt
├── .env.example                 # ローカル用の環境変数サンプル(値は空)
├── .gitignore
├── credit_snippet.html          # Yahoo!クレジット表示(サイトフッター貼り付け用、社長作業)
├── blog_auto_post/
│   ├── config.py                # 環境変数読み込み
│   ├── topics.py                 # トピックキュー管理(Dragonと無改修で共通ロジック)
│   ├── yahoo_client.py           # Yahoo!ショッピングAPI連携 + レートリミッタ(未検証実装)
│   ├── affiliate.py              # バリューコマース アフィリエイトURL変換(現状プレースホルダー)
│   ├── scoring.py                # 独自スコアリング・買い時判定ロジック(Dragonと無改修で共通)
│   ├── price_history.py          # 価格推移データの蓄積・参照(Dragonと無改修で共通)
│   ├── table_builder.py          # 比較表HTML・クレジット表示・免責文言の組み立て
│   ├── article_pipeline.py       # Claude APIによる段階分割の記事生成(ガジェット向け文言)
│   └── hatena_client.py          # はてなブログAtomPub API連携(Dragonと無改修で共通)
├── data/
│   ├── topics.json               # トピック候補(型落ちガジェット、初期12件)
│   └── price_history.json        # 商品コード別の価格スナップショット履歴(実行のたびに追記)
└── .github/workflows/
    └── daily-post.yml            # 毎日JST 10:00に自動実行するscheduled workflow(Dragonの9:00とずらす)
```

## 必要な環境変数

| 変数名 | 説明 | 現状 |
|---|---|---|
| `ANTHROPIC_API_KEY` | Claude APIキー | 既存キーを流用可能(Dragonと共通のANTHROPIC_API_KEYを使う想定) |
| `CLAUDE_MODEL` | 記事生成モデル(省略時デフォルト `claude-sonnet-5`) | 設定不要 |
| `HATENA_ID` | はてなID | **未取得**(ブログ開設後に判明) |
| `HATENA_BLOG_DOMAIN` | ブログドメイン | `kataochi-gadget-hikakusho.hatenablog.com`(確定済み) |
| `HATENA_API_KEY` | はてなブログのAtomPub APIキー(管理画面の詳細設定→AtomPub欄) | **未取得**(ブログ開設後に発行) |
| `YAHOO_CLIENT_ID` | Yahoo!デベロッパーネットワークで発行される「Client ID」 | **未取得** |
| `VC_AFFILIATE_ID` | バリューコマースのアフィリエイトID | ASP審査通過まで空文字運用でOK |

**注意: 実際のAPIキーはコード・READMEに直接書かず、必ず環境変数(`.env`またはGitHub Secrets)経由で渡してください。**

## 社長への依頼事項チェックリスト

以下はコード実装では対応できず、社長ご自身の手作業が必要です。完了次第、値を
developer(私)またはこのリポジトリのGitHub Secretsへ共有してください。

- [ ] **はてなブログの新規開設**: はてなアカウントで新しいブログを作成し、ブログ名
      「型落ちガジェット比較所」、ブログURL(サブドメイン)を
      `kataochi-gadget-hikakusho.hatenablog.com` に設定する
      (既にDragon用のはてなアカウントがある場合、同一アカウント内で複数ブログ運用が
      可能かどうかも要確認。不可の場合は新規はてなアカウント作成が必要)
- [ ] **はてなブログAtomPub APIキーの取得**: 開設したブログの管理画面 →
      「設定」→「詳細設定」→「AtomPub」欄でAPIキーを発行する(`HATENA_API_KEY`)
- [ ] **Yahoo!デベロッパーネットワークへの登録・Client ID取得**:
      https://e.developer.yahoo.co.jp/register/ からアプリケーション登録を行い、
      「Client ID」を発行する(`YAHOO_CLIENT_ID`)。登録時に「許可されたWebサイト」等
      ドメイン登録を求められる場合は上記のはてなブログドメインを指定する
      (Dragon側で楽天ウェブサービス新API仕様が「Origin登録ドメイン一致必須」だった
      前例があるため、Yahoo側も同様の可能性を考慮しておくこと)
- [ ] **クレジット表示スニペットの設置**: 本ディレクトリの `credit_snippet.html` の
      中身を、開設したはてなブログの管理画面 → デザイン → カスタマイズ →
      フッタ(またはサイドバー最下部)に**改変せずそのまま**貼り付ける
      (Yahoo!デベロッパーネットワーク規約上の必須対応。詳細は`credit_snippet.html`
      内コメントおよび `../developer/tasks.md` の
      「秘書によるクレジット表示文言の確認」セクション参照)
- [ ] **バリューコマースへのメディア(サイト)登録申請**: `../developer/tasks.md`の
      マイルストーン通り、記事14本前後蓄積した時点(Week 2目安)で申請。
      通過後、ビックカメラ・ノジマ・エディオンの各広告主プログラムへ個別申請し、
      承認された広告主のアフィリエイトIDを`VC_AFFILIATE_ID`として設定する
- [ ] **GitHubリポジトリの新規作成**: Dragonとは別リポジトリ(例: `sacred-abyss-angel`、
      命名は既にCEO/マーケ判断待ちと `developer/tasks.md` に記載済み)を作成し、
      本ディレクトリの中身をpushする。Secretsに上記環境変数一覧を登録する
- [ ] **(参考、必須ではない)** Yahoo!ショッピングAPI公式ドキュメント
      (https://developer.yahoo.co.jp/webapi/shopping/v3/itemsearch.html)の実物を
      Client ID取得後に確認し、`yahoo_client.py`内の「要検証」コメント箇所
      (エンドポイントURL・レスポンスのフィールド名)を実際の仕様に合わせて修正する
      作業が必要(こちらは developer 側で対応可能。Client ID発行さえ完了すれば
      着手できる)

## ローカルでのテスト実行方法

1. Python 3.11以上をインストール
2. 依存パッケージのインストール
   ```
   cd angel/app
   python -m venv venv
   venv\Scripts\activate        (Windowsの場合)
   pip install -r requirements.txt
   ```
3. `.env.example` を `.env` にコピーし、実際のAPIキーを入力する
   ```
   copy .env.example .env
   ```
   上記チェックリストで取得した`HATENA_ID` / `HATENA_API_KEY` / `YAHOO_CLIENT_ID`等を
   設定してください。
4. 実行
   ```
   python main.py
   ```
   成功すると、標準出力に選定トピック・取得商品数・生成タイトル・投稿URLが表示されます。
   本パイプラインは要件通り「完全自動公開」(下書きを経由しない)で実装されているため、
   ローカル実行でも実際に本番ブログへ即公開される点に注意してください。

   実行のたびに `data/topics.json`(使用済みマーク)と `data/price_history.json`(価格スナップショット)
   が更新されます。テストで実際にブログへ投稿したくない場合は、`main.py` の
   `post_entry(...)` 呼び出し部分を一時的にコメントアウトするか、ダミーの
   `HATENA_API_KEY` のままにして「はてな投稿失敗」で止まる状態(=そこより前の
   処理だけ確認する)にしてください。

## GitHub Secretsへの登録方法

1. GitHubリポジトリの「Settings」→「Secrets and variables」→「Actions」→「New repository secret」
2. 以下の名前でそれぞれ値を登録:
   - `ANTHROPIC_API_KEY`
   - `HATENA_ID`
   - `HATENA_BLOG_DOMAIN`
   - `HATENA_API_KEY`
   - `YAHOO_CLIENT_ID`
   - `VC_AFFILIATE_ID`(未提携でも空文字で登録しておくと安全)
3. `.github/workflows/daily-post.yml` はこれらを `${{ secrets.XXX }}` の形式で参照します。

## GitHub Actionsの動作

- 毎日 UTC 1:00(= JST 10:00)に自動実行(`.github/workflows/daily-post.yml`)。
  Dragon(JST 9:00)と実行時刻をずらしてあります。実行時刻はGitHub Actions側の
  ベストエフォートのため数分〜のズレが生じ得ます。
- `workflow_dispatch` にも対応しているため、Actionsタブから手動実行して動作確認も可能です。
- 実行成功後、更新された `data/topics.json` / `data/price_history.json` を
  ワークフロー自身が自動コミット・pushします。このコミットには
  `permissions: contents: write` が必要です(デフォルトのGITHUB_TOKENで動作します)。

## エラー通知(拡張ポイント)

現状は実行失敗時にGitHub Actionsの実行ログ(`::error::`形式)に出力するのみです。
`main.py` の `notify_failure()` 関数と、`daily-post.yml` 内のコメントアウトされた
Discord Webhook送信ステップの例を拡張ポイントとして残しています。

## 既知の制約・注意点(PoCスコープ)

- **Yahoo!ショッピングAPIレスポンス構造は未検証**: `yahoo_client.py`のエンドポイント
  URL・レスポンスフィールド名は公開情報からの推測実装です。Client ID取得後、実機で
  動作確認・修正が必須です(上記チェックリスト参照)。
- **アフィリエイトURL変換は未実装**: `affiliate.py`の`to_affiliate_url()`は
  バリューコマース提携前提のプレースホルダーです。ASP審査通過後、実際のリンク
  変換ロジック(sid/pid等の必須パラメータ)を実装する必要があります。
- **クレジット表示の二重設置**: `table_builder.build_credit_html()`で記事本文
  (比較表直後)にも設置していますが、公式要件は「サイト下部1箇所」で充足するため、
  `credit_snippet.html`のフッター設置さえ行えば記事側は省略しても規約違反には
  なりません(`../developer/tasks.md`参照)。
- **画像**: Yahoo!ショッピングAPIから取得した商品画像URLを直接埋め込みます(ホットリンク)。
  画像利用に関する規約上の制約(トリミング・改変可否等)は未確認のため、実機動作確認時に
  Yahoo!デベロッパーネットワークの利用規約を再確認すること。
- **価格推移データ**: Yahoo!ショッピングAPIも過去の価格履歴を提供しないため、
  本スクリプトを実行するたびに `data/price_history.json` へスナップショットを
  蓄積していく方式です。運用開始直後は「今回から価格追跡を開始しました」という
  表示になり、実行を重ねるほど実際の推移が表示されます。
- **トピックキュー**: 初期12件を使い切ると自動的に全件リセットして再利用します。
  トピックを増やしたい場合は `data/topics.json` に同じ形式で追記してください。

## コスト目安

Claude Sonnet 5使用、1記事あたり4回のAPI呼び出し(アウトライン/本文/タイトル/自己レビュー)で
約$0.04程度(概算、Dragonと同水準)。Yahoo!ショッピングAPI自体は無料利用枠(50,000req/日)の
範囲内で収まる見込み(詳細は`../developer/tasks.md`のレート制限検討参照)。
