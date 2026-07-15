"""Claude API(Sonnet 5)を使った段階分割の記事生成パイプライン。

①アウトライン生成 → ②本文生成 → ③タイトル/メタディスクリプション生成 → ④自己レビュー
の4段階に分けて呼び出す。Yahoo!ショッピングAPIから取得した実データ(価格・レビュー・スコア)を
各プロンプトに埋め込み、価格等の具体的数値はLLMに創作させず、既存データの参照・
言い換えに留めるよう明示的に指示する。

Dragon(app/blog_auto_post/article_pipeline.py)と同一の4段階構成・API呼び出しロジックだが、
ブログ「型落ちガジェット比較所」向けにプロンプト文言をガジェット(スマートフォン・イヤホン・
タブレット・カメラ等)前提の内容へ差別化している(家電量販店の販売経験という設定は流用せず、
ガジェット領域向けの人物設定に変更)。
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import Any

import anthropic

from .table_builder import PRODUCT_TABLE_PLACEHOLDER

MAX_TOKENS_OUTLINE = 1536
MAX_TOKENS_BODY = 8192
MAX_TOKENS_TITLE = 512
MAX_TOKENS_REVIEW = 8192

FINAL_BODY_MARKER = "### FINAL_BODY"


class TruncatedResponseError(RuntimeError):
    """Claude APIの応答がmax_tokens上限で打ち切られた場合に送出する。"""


@dataclass
class ArticleDraft:
    outline: str
    body_html: str
    title: str
    meta_description: str
    review_notes: str


def _format_products_for_prompt(products: list[dict[str, Any]]) -> str:
    lines = []
    for i, p in enumerate(products, start=1):
        price = f"¥{p['price']:,}" if p.get("price") else "価格不明"
        lines.append(
            f"{i}. {p.get('name', '')}\n"
            f"   価格: {price} / ショップ: {p.get('shop_name', '')}\n"
            f"   レビュー: 平均{p.get('review_average', 0):.1f} "
            f"({p.get('review_count', 0)}件)\n"
            f"   独自スコア: {p.get('buy_score', '-')}/100 判定: {p.get('judgment', '-')}\n"
            f"   商品説明抜粋: {str(p.get('item_caption', ''))[:150]}"
        )
    return "\n".join(lines)


class ArticlePipeline:
    def __init__(self, api_key: str, model: str):
        self._client = anthropic.Anthropic(api_key=api_key)
        self._model = model

    def _call(
        self,
        system: str,
        user_content: str,
        max_tokens: int,
        raise_on_truncation: bool = False,
    ) -> str:
        resp = self._client.messages.create(
            model=self._model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user_content}],
        )
        text = "".join(
            block.text for block in resp.content if getattr(block, "type", "") == "text"
        ).strip()
        if resp.stop_reason == "max_tokens":
            if raise_on_truncation:
                # タイトル生成のように短く構造化された出力を期待する箇所でのみ送出する。
                # 呼び出し側でmax_tokensを引き上げて再試行 or フォールバックする。
                raise TruncatedResponseError(
                    f"応答がmax_tokens={max_tokens}で打ち切られました: {text!r}"
                )
            # 本文・アウトライン・自己レビューのような長文生成では、打ち切られても
            # 例外にしてパイプライン全体を落とす(=その日の投稿がゼロになる)より、
            # 多少短い記事を出す方が安全なため、警告のみ出して打ち切られたテキストを返す。
            print(
                f"::warning::応答がmax_tokens={max_tokens}で打ち切られました(処理は継続)",
                file=sys.stderr,
            )
        return text

    # ------------------------------------------------------------------
    # ① アウトライン生成
    # ------------------------------------------------------------------
    def generate_outline(self, topic_title: str, category: str, products_text: str) -> str:
        system = (
            "あなたは型落ち・旧モデルガジェット(スマートフォン・タブレット・イヤホン・"
            "スマートウォッチ・カメラ・PC周辺機器等)比較サイト「型落ちガジェット比較所」の"
            "専門編集者です。価格.comやマイベストのような大手比較サイトが手薄な"
            "「型落ちモデル vs 最新モデル、型落ちを買うべきか」という切り口に特化し、"
            "読者が購入判断できる記事のアウトラインを作ります。"
            "SEOを強く意識し、読者が実際に検索しそうな悩み・比較観点を見出しに反映させます。"
        )
        user = f"""以下のトピックと商品データをもとに、記事の見出し構成(アウトライン)を
Markdownの見出しリスト形式で出力してください。各見出しに1〜2行で要点も添えてください。

トピック: {topic_title}
カテゴリ: {category}

商品データ(Yahoo!ショッピングAPI取得):
{products_text}

出力要件:
- 見出しは## から始めるMarkdown形式のみ
- 「型落ちモデルと最新モデルの違い」「価格差と価値」「独自スコアによる買い時判定」
  「どんな人に型落ちがおすすめか」「購入前によくある疑問・注意点」「実際に選ぶ際のチェックポイント」
  といった観点を必ず含め、記事のボリュームを確保する
- SEOタイトルで想定される検索意図(例:「型落ち ○○ 買うべきか」「型落ち ○○ デメリット」)を
  意識した見出しを2つ以上含める
- 商品比較表を挿入するべき見出しの直後に「(ここに比較表)」と明記する
- 見出しは8〜10個程度(本文を2800字以上に伸ばせるボリューム感にする)
"""
        return self._call(system, user, MAX_TOKENS_OUTLINE)

    # ------------------------------------------------------------------
    # ② 本文生成
    # ------------------------------------------------------------------
    def generate_body(
        self, topic_title: str, category: str, products_text: str, outline: str
    ) -> str:
        system = (
            "あなたはガジェットショップでの販売経験と、型落ち品を狙って自分でも"
            "スマートフォンやガジェットを買い替えてきた実体験を持つ、"
            "「型落ちガジェット比較所」の専門ライターです。"
            "無機質でテンプレ的な『AIが書いたような』文章ではなく、生活者目線の具体的な言葉づかい"
            "(例: 「正直〜」「実際に使うシーンを想像すると」「筆者の感覚では」といった一人称の実感を伴う"
            "言い回し)を随所に混ぜ、血の通った読み物として仕上げてください。"
            "ただし価格や仕様等の具体的な数値は、必ずプロンプトで与えられたデータの範囲内でのみ言及し、"
            "与えられていない数値や型番の詳細スペック・個人の体験談の細部(具体的な日付や個人の生活描写等)"
            "を事実として創作してはいけません。データにない体験は「多くのユーザーは〜と感じるようです」"
            "のように一般化した表現に留めてください。"
            "SEOも強く意識し、想定読者が検索するであろう疑問文・キーワードを自然な文章の中に"
            "繰り返し織り込んでください。"
        )
        user = f"""以下のアウトラインに沿って、記事本文をHTML形式で執筆してください。

トピック: {topic_title}
カテゴリ: {category}

商品データ(Yahoo!ショッピングAPI取得、この範囲内の情報のみ本文で言及すること):
{products_text}

アウトライン:
{outline}

出力要件(文体・トーン):
- 「〜です・ます」調をベースに、時々「〜ですよね」「〜と感じる方も多いはずです」といった
  読者に語りかける表現を混ぜ、機械的な箇条書き偏重ではなく地の文の説明を厚めにする
- 冒頭は「型落ちを検討している読者が抱えていそうな悩み・迷い」に共感する導入文から始める
  (例: 「そろそろ買い替えたいけど型落ちで妥協して後悔しないか不安、という方へ」等)
- 各セクションの結論だけでなく「なぜそう言えるのか」という理由付け・背景説明を1〜2文加える
- 見出しごとに最低150〜250字程度の説明量を確保し、内容が薄くならないようにする

出力要件(SEO):
- タイトル候補になりうる主要キーワード(「型落ち」+商品カテゴリ名等)を本文中に自然な頻度で
  繰り返し登場させる(不自然な詰め込みは避ける)
- 「型落ち ○○ 買うべきか」「型落ち ○○ デメリット」「型落ち ○○ 選び方」等、検索されやすい
  疑問形の見出し・小見出しを最低2つ含める
- 記事末尾に、読者の疑問に答えるQ&A形式のセクション(3問程度)を含める

出力要件(技術仕様):
- HTMLタグ(<h2>, <h3>, <p>, <ul><li>, <strong>等)を使い、はてなブログにそのまま貼り付けられる形式にする
- <html>や<body>などの外枠タグは不要。本文の中身のみ出力する
- アウトラインで「(ここに比較表)」と指定された箇所に、プレースホルダー文字列
  `{PRODUCT_TABLE_PLACEHOLDER}` を単独の行として必ず1箇所挿入する(表自体はこちらでは生成しない)
- 商品名・価格・レビュー件数などの具体的な数値は上記データの記載範囲に忠実にする
- 独自スコア・判定(買い時/妥当/様子見)についても触れ、その根拠(レビュー評価・件数・価格の割安度から
  機械的に算出していること)を簡潔に説明する
- 文字数目安は本文全体で3000〜4000字程度(Q&A・まとめ含む)。薄くなるくらいなら具体例を足して伸ばす
- 冒頭に導入文、末尾に「まとめ」の見出しとQ&Aセクションを含める
"""
        body = self._call(system, user, MAX_TOKENS_BODY)
        if PRODUCT_TABLE_PLACEHOLDER not in body:
            # プレースホルダーが挿入されなかった場合のフォールバック:
            # 最初の</h2>の後、なければ本文末尾に追加する
            body = body + f"\n{PRODUCT_TABLE_PLACEHOLDER}\n"
        return body

    # ------------------------------------------------------------------
    # ③ タイトル/メタディスクリプション生成
    # ------------------------------------------------------------------
    def generate_title_and_meta(self, topic_title: str, body_html: str) -> tuple[str, str]:
        system = (
            "あなたはSEOに強いタイトル・メタディスクリプションの専門家です。"
            "クリックされやすく、かつ内容を誇張しないタイトルを作ります。"
        )
        user = f"""以下は記事本文(HTML)です。この記事にふさわしいSEOタイトルと
メタディスクリプションを考えてください。

トピック: {topic_title}

本文:
{body_html[:3000]}

出力形式は厳密に以下の2行のみ(他の説明文は一切出力しないこと):
TITLE: (32文字前後のタイトル)
META: (110〜120文字程度のメタディスクリプション)
"""
        try:
            raw = self._call(system, user, MAX_TOKENS_TITLE, raise_on_truncation=True)
        except TruncatedResponseError:
            # 前置きの説明文等で出力が長くなりmax_tokensで打ち切られたケース。
            # 上限を上げて1回だけ再試行し、それでも打ち切られたらフォールバックへ委ねる。
            try:
                raw = self._call(
                    system, user, MAX_TOKENS_TITLE * 2, raise_on_truncation=True
                )
            except TruncatedResponseError:
                raw = ""

        title = topic_title
        meta = ""
        for line in raw.splitlines():
            line = line.strip()
            if line.startswith("TITLE:"):
                title = line[len("TITLE:"):].strip()
            elif line.startswith("META:"):
                meta = line[len("META:"):].strip()

        # タイトル途中切れバグ対策: 極端に短い(=生成途中で切れた)場合はtopic_titleへフォールバック
        if len(title) < 10:
            title = topic_title
        return title, meta

    # ------------------------------------------------------------------
    # ④ 自己レビュー(誤情報・薄い内容チェック)
    # ------------------------------------------------------------------
    def self_review(
        self, topic_title: str, products_text: str, body_html: str
    ) -> tuple[str, str]:
        system = (
            "あなたは編集責任者として、公開前の記事をレビューする校閲者です。"
            "Googleの「Scaled Content Abuse」ポリシー(独自性のない量産的低品質コンテンツへの対策)"
            "を踏まえ、以下の観点をチェックしてください。"
            "1) 与えられた商品データにない事実(価格・型番・スペック・具体的な個人の体験談の細部)を"
            "創作していないか"
            "2) 内容が薄すぎないか(具体性のない一般論だけになっていないか、文字数目安3000〜4000字に"
            "対して極端に短くなっていないか)"
            "3) 読者にとっての実用的な結論(型落ちと最新どちらを選ぶべきか)が明確か"
            "4) 文体が血の通った読み物になっているか(テンプレ的・機械的な言い回しが目立つ場合は、"
            "生活者目線の自然な言葉づかいに直す。ただし内容の薄さと違って文体だけを理由に大きく"
            "文字数を削らないこと)"
        )
        user = f"""トピック: {topic_title}

商品データ(事実確認用):
{products_text}

レビュー対象の記事本文(HTML):
{body_html}

上記の観点でレビューし、必要なら本文を改善（誤情報の削除・薄い部分の補強・結論の明確化）した上で、
以下の形式で厳密に出力してください(他の文言を前後に含めないこと)。
問題がなければ本文をそのまま「{FINAL_BODY_MARKER}」以降にコピーしてください。

### REVIEW_NOTES
(チェック結果を2〜4行程度の箇条書きで。指摘がなければ「問題なし」とだけ書く)

{FINAL_BODY_MARKER}
(最終版の本文HTML。{PRODUCT_TABLE_PLACEHOLDER} のプレースホルダー行は必ずそのまま残すこと)
"""
        raw = self._call(system, user, MAX_TOKENS_REVIEW)

        if FINAL_BODY_MARKER in raw:
            notes_part, body_part = raw.split(FINAL_BODY_MARKER, 1)
            notes = notes_part.replace("### REVIEW_NOTES", "").strip()
            final_body = body_part.strip()
        else:
            # マーカーが見つからない場合は安全側に倒し、レビュー前の本文をそのまま使う
            notes = "(レビュー出力のパースに失敗したため、レビュー前の本文をそのまま採用)"
            final_body = body_html

        if PRODUCT_TABLE_PLACEHOLDER not in final_body:
            final_body = final_body + f"\n{PRODUCT_TABLE_PLACEHOLDER}\n"

        return final_body, notes

    # ------------------------------------------------------------------
    def run(self, topic_title: str, category: str, products: list[dict[str, Any]]) -> ArticleDraft:
        products_text = _format_products_for_prompt(products)

        outline = self.generate_outline(topic_title, category, products_text)
        body = self.generate_body(topic_title, category, products_text, outline)
        final_body, review_notes = self.self_review(topic_title, products_text, body)
        # タイトルは自己レビュー後の最終本文を見て決定する(2026-07-15修正: 従来は
        # レビュー前のbodyでタイトルを決めていたため、自己レビューが本文中の誇大表現・
        # データ不整合(例: 商品データに存在しないメーカー名への言及)を修正しても、
        # 既に確定したタイトルには反映されず、タイトルと本文の内容が食い違う実例を
        # ドライラン検証(実際のClaude API呼び出し)で確認したため、呼び出し順序を入れ替えた)
        title, meta = self.generate_title_and_meta(topic_title, final_body)

        return ArticleDraft(
            outline=outline,
            body_html=final_body,
            title=title,
            meta_description=meta,
            review_notes=review_notes,
        )
