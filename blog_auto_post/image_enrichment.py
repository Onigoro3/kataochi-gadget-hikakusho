"""記事への画像挿入(アイキャッチ・テーマ画像)。

2026-07-20、`last_minute_hotel_navi/image_enrichment.py`(Dragonリポジトリ)で実装・実機検証
した設計をAngel(型落ちガジェット比較所)へ横展開したもの。Dragon本体(app/blog_auto_post/
image_enrichment.py)と全く同じロジック。2種類の画像ソースを組み合わせる:

1. アイキャッチ: 楽天市場APIで既に取得済みの独自スコア(buy_score)1位商品の画像を
   そのまま使う(追加コスト・追加API連携が一切不要)。はてなブログは「本文中の最初の画像」を
   自動でアイキャッチ(記事のサムネイル)に採用する仕様のため、本文冒頭に挿入するだけで機能する。
2. テーマ画像(段落区切り用): Angelの記事もDragonと同型のH2構成(型落ちvs最新モデルの比較)が
   続き、hotel_naviのような繰り返し名詞見出し(<h3>ループ)は存在しない(実際の本番記事
   https://kataochi-gadget-hikakusho.hatenablog.com/entry/2026/07/19/133044 で確認済み)。
   そのため「イントロ段落の直後・比較の本題(最初のH2)に入る前」の1箇所に、記事テーマ
   (ガジェットカテゴリ)に関連する一般的な写真を1枚だけ挿入する設計にした。

いずれの画像挿入も「取得できなければ何も挿入せず記事本文はそのまま」というフェイルセーフ設計
(既存モジュールと同じ「1箇所の失敗で全体を止めない」方針を踏襲)。

【重要・実機で得た教訓】Pexelsは日本語クエリのままだと無関係な画像がヒットしやすい
(hotel_naviで「新宿御苑」検索が無関係なケーキ写真を返した実例あり。0件でも何らかの写真を
返すフォールバック挙動があるため「ヒットしない」による自動検出もできない)。そのため
テーマ画像の検索クエリは`ArticlePipeline.translate_theme_query()`でClaudeに英語へ変換させて
から検索する(本モジュールでは変換済みクエリを受け取るだけで、変換自体は行わない)。
"""
from __future__ import annotations

import re
from html import escape

_H2_PATTERN = re.compile(r"<h2[^>]*>", re.IGNORECASE)


def build_image_html(image_url: str, alt_text: str) -> str:
    """画像1枚分のHTML(クレジット表記なし)を組み立てる。アイキャッチ用。"""
    if not image_url:
        return ""
    return (
        f'<p><img src="{escape(image_url)}" alt="{escape(alt_text)}" '
        'style="max-width:100%;height:auto;border-radius:6px;"></p>'
    )


def insert_eyecatch(body_html: str, image_url: str, alt_text: str) -> str:
    """本文の先頭にアイキャッチ画像を挿入する(取得できなければ本文をそのまま返す)。"""
    eyecatch_html = build_image_html(image_url, alt_text)
    if not eyecatch_html:
        return body_html
    return eyecatch_html + "\n" + body_html


def build_pexels_image_html(photo: dict, alt_text: str) -> str:
    """Pexels由来のテーマ画像HTML(撮影者クレジット付き)を組み立てる。"""
    return (
        f'<p><img src="{escape(photo["image_url"])}" alt="{escape(alt_text)}" '
        'loading="lazy" style="max-width:100%;height:auto;border-radius:6px;">'
        f'<br><small style="color:#999;">Photo by '
        f'<a href="{escape(photo["photographer_url"])}" target="_blank" rel="nofollow noopener">'
        f'{escape(photo["photographer"])}</a> on '
        f'<a href="{escape(photo["pexels_url"])}" target="_blank" rel="nofollow noopener">Pexels</a>'
        "</small></p>"
    )


def insert_theme_image_before_first_h2(body_html: str, photo: dict | None, alt_text: str) -> str:
    """イントロ段落の直後・最初の<h2>見出しの直前にテーマ画像を1枚挿入する。

    Angelの記事は必ずイントロ文の後に最初のH2(型落ちvs最新モデルの比較の本題)が
    来る構成のため、この位置が「段落を区切る画像」として最も自然。<h2>が本文中に
    見つからない場合(想定外の出力)は何もせず本文をそのまま返す(フェイルセーフ)。
    """
    if photo is None:
        return body_html
    image_html = build_pexels_image_html(photo, alt_text)

    match = _H2_PATTERN.search(body_html)
    if not match:
        return body_html
    idx = match.start()
    return body_html[:idx] + image_html + "\n" + body_html[idx:]
