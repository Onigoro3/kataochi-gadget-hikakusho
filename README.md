# Angel部門 完全自動投稿ブログ(型落ちガジェット比較所)

投稿先ブログ: `https://kataochi-gadget-hikakusho.hatenablog.com/`(2026-07-13 本番稼働開始)

トピック選択 → 楽天市場API(商品検索API)で型落ち/最新モデルのガジェット商品データ取得
→ 独自スコアリング(買い時判定) → Claude API(Sonnet 5)で記事生成
(アウトライン → 本文 → タイトル/メタ → 自己レビュー) → はてなブログへ**公開状態で**
自動投稿、までを1回の実行で行うパイプラインです。GitHub Actionsで毎日自動実行します。

Dragon部門(`../../app/`、型落ち家電ラボ)の実装を土台に移植した構成です。

**2026-07-14、データソースをYahoo!ショッピングAPIから楽天市場API(Dragonと同一)へ
切り替え**。社長判断により「Dragon・Angelを同じ楽天データで直接対決させる」方針に変更
(Yahoo!ショッピングAPIの運用上の不便を解消するため)。差別化は部署間で共通データソースを
使いつつ、トピックの切り口(Dragon=白物家電・季節家電、Angel=カメラ・スマホ・オーディオ等の
デジタルガジェット)で担保する。旧Yahoo!版の実装・クレジット表示要件は撤去済み。

## 構成

```
angel/app/
├── main.py                     # メイン実行スクリプト(1回分のパイプライン)
├── requirements.txt
├── .env.example                 # ローカル用の環境変数サンプル(値は空)
├── .gitignore
├── blog_auto_post/
│   ├── config.py                # 環境変数読み込み
│   ├── topics.py                 # トピックキュー管理(Dragonと無改修で共通ロジック)
│   ├── rakuten_client.py         # 楽天市場API連携(Dragonと完全に同一、2026-07-14移植)
│   ├── scoring.py                # 独自スコアリング・買い時判定ロジック(Dragonと無改修で共通)
│   ├── price_history.py          # 価格推移データの蓄積・参照(Dragonと無改修で共通)
│   ├── table_builder.py          # 比較表HTML・免責文言の組み立て(Dragonと同一実装)
│   ├── article_pipeline.py       # Claude APIによる段階分割の記事生成(ガジェット向け文言)
│   └── hatena_client.py          # はてなブログAtomPub API連携(Dragonと無改修で共通)
├── data/
│   ├── topics.json               # トピック候補(型落ちガジェット、初期12件)
│   └── price_history.json        # 商品コード別の価格スナップショット履歴(実行のたびに追記)
└── .github/workflows/
    └── daily-post.yml            # 毎日JST 10:00に自動実行するscheduled workflow(Dragonの9:00とずらす)
```

## 必要な環境変数

| 変数名 | 説明 |
|---|---|
| `ANTHROPIC_API_KEY` | Claude APIキー(Dragonと共通のキーを使用) |
| `CLAUDE_MODEL` | 記事生成モデル(省略時デフォルト `claude-sonnet-5`) |
| `HATENA_ID` | はてなID(`MagicaiAngel`、Dragonとは別アカウント) |
| `HATENA_BLOG_DOMAIN` | `kataochi-gadget-hikakusho.hatenablog.com` |
| `HATENA_API_KEY` | はてなブログのAtomPub APIキー |
| `RAKUTEN_APP_ID` | 楽天ウェブサービスのアプリID(2026-07-14追加、Angel専用に新規発行した値。Dragonとは別) |
| `RAKUTEN_ACCESS_KEY` | 楽天ウェブサービスの2026年新API仕様で必須のアクセスキー(Angel専用アプリの値) |
| `RAKUTEN_AFFILIATE_ID` | 楽天アフィリエイトID(Dragonと同じ値。同一アフィリエイト口座に収益を集約) |

**注意: 実際のAPIキーはコード・READMEに直接書かず、必ず環境変数(`.env`またはGitHub Secrets)経由で渡してください。**

### 楽天API側のドメイン登録(2026-07-14 対応済み)

楽天ウェブサービスAPIの2026年新仕様では、APIリクエストの`Origin`ヘッダーが
アプリ登録時の「許可されたWebサイト」と一致しないと403エラーになる
(`blog_auto_post/rakuten_client.py`のdocstring参照)。楽天デベロッパーの登録は
「1アプリ=1URL」単位(既存アプリへのドメイン追加登録はできない仕様)と判明したため、
DragonのRakutenアプリ(`magicaidrop.hatenablog.com`用)を共用するのではなく、
**Angel専用の新規アプリ「型落ちガジェット比較書」を発行**(アプリURL:
`kataochi-gadget-hikakusho.hatenablog.com`、アフィリエイトIDはDragonと同じものを選択)。
新しいアプリID・アクセスキーで実際に商品データを取得できることを確認済み。

## 社長への依頼事項チェックリスト(2026-07-14 楽天切り替え分)

- [x] ~~楽天デベロッパー管理画面でAngelのブログドメインを許可Webサイトに追加登録~~
      → Angel専用の新規アプリ発行で対応済み(上記参照)
- [ ] **GitHub Secretsの更新**: `Onigoro3/kataochi-gadget-hikakusho`リポジトリの
      Settings → Secrets and variables → Actions で以下を登録・更新
      - `RAKUTEN_APP_ID`(新規追加、Angel専用の値)
      - `RAKUTEN_ACCESS_KEY`(新規追加、Angel専用の値)
      - `RAKUTEN_AFFILIATE_ID`(未登録なら追加、Dragonと同じ値)
      - `YAHOO_CLIENT_ID` / `VC_AFFILIATE_ID` は不要になったため削除して構わない(残しても実害はない)
- [ ] **はてなブログのフッターからYahoo!クレジット表示を削除**: 管理画面 → デザイン →
      カスタマイズ → フッタに設置していた「Webサービス by Yahoo! JAPAN」表示は、
      Yahoo!ショッピングAPIを使わなくなったため不要(義務ではなくなった)。削除してよい
- [ ] 上記が完了したら、ローカルまたは`workflow_dispatch`の手動実行で楽天APIが
      正常に動作するか(403にならないか)を確認する

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
4. 実行
   ```
   python main.py
   ```
   成功すると、標準出力に選定トピック・取得商品数・生成タイトル・投稿URLが表示されます。
   本パイプラインは「完全自動公開」(下書きを経由しない)で実装されているため、
   ローカル実行でも実際に本番ブログへ即公開される点に注意してください。
   投稿せずに内容だけ確認したい場合は環境変数 `ANGEL_DRY_RUN=true` を設定して実行する
   (`post_entry()` を呼ばず、投稿予定タイトル・本文冒頭を標準出力するだけに留まる)。

   実行のたびに `data/topics.json`(使用済みマーク)と `data/price_history.json`(価格スナップショット)
   が更新されます。

## GitHub Actionsの動作

- 毎日 UTC 1:00(= JST 10:00)に自動実行(`.github/workflows/daily-post.yml`)。
  Dragon(JST 9:00)と実行時刻をずらしてあります。
- `workflow_dispatch` にも対応しているため、Actionsタブから手動実行して動作確認も可能です。
- 実行成功後、更新された `data/topics.json` / `data/price_history.json` を
  ワークフロー自身が自動コミット・pushします。

## エラー通知(拡張ポイント)

現状は実行失敗時にGitHub Actionsの実行ログ(`::error::`形式)に出力するのみです。
`main.py` の `notify_failure()` 関数と、`daily-post.yml` 内のコメントアウトされた
Discord Webhook送信ステップの例を拡張ポイントとして残しています。

## 既知の制約・注意点

- **画像**: 楽天APIから取得した商品画像URLを直接埋め込みます(ホットリンク)。
- **価格推移データ**: 楽天APIも過去の価格履歴を提供しないため、本スクリプトを実行する
  たびに `data/price_history.json` へスナップショットを蓄積していく方式です。検索結果は
  トピックごとに変わり同一商品が再登場するとは限らないため、2回目以降の計測がない商品には
  注記を表示しません(2026-07-14修正: 以前は「今回から価格追跡を開始しました」を毎回
  表示していたが、ほぼ全商品に該当し記事が同じ文言だらけになっていたため撤去)。
- **トピックキュー**: 初期12件を使い切ると自動的に全件リセットして再利用します。
  トピックを増やしたい場合は `data/topics.json` に同じ形式で追記してください。
- **Dragonとの重複コンテンツリスク**: 同じ楽天データを扱う以上、同一商品が両ブログに
  掲載されうる。トピックの切り口(ジャンル)を明確に分けることで差別化を維持する運用。

## コスト目安

Claude Sonnet 5使用、1記事あたり4回のAPI呼び出し(アウトライン/本文/タイトル/自己レビュー)で
約$0.04程度(概算、Dragonと同水準)。楽天APIは無料利用枠の範囲内で収まる見込み。
