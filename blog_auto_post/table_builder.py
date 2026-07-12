"""比較表(HTML)・クレジット表示・免責文言の組み立て。

価格・型番・スペック等の実データはLLMに生成させず、Yahoo!ショッピングAPIから取得した値を
そのままコードで整形する(ハルシネーション防止・数値の正確性担保のため)。
LLMにはこの完成済みHTMLブロックを記事内の適切な位置に挿入させる形で連携する。

Dragon(app/blog_auto_post/table_builder.py)の `build_comparison_table_html()` は
無改修で流用(yahoo_client.py側で楽天版と同一の内部スキーマへ正規化済みのため)。
`build_disclaimer_html()` は文言をYahoo!ショッピングAPI向けに調整。
`build_credit_html()` はAngel独自の追加(Yahoo!デベロッパーネットワークのクレジット表示義務対応)。
"""
from __future__ import annotations

from html import escape
from typing import Any

PRODUCT_TABLE_PLACEHOLDER = "<!--PRODUCT_TABLE-->"


def build_comparison_table_html(
    products: list[dict[str, Any]],
    trend_notes: dict[str, str] | None = None,
) -> str:
    """商品一覧から比較表HTMLを生成する。"""
    trend_notes = trend_notes or {}

    rows = []
    for p in products:
        name = escape(p.get("name", ""))
        price = p.get("price")
        price_text = f"¥{price:,}" if price else "価格情報なし"
        image_url = escape(p.get("image_url", ""))
        url = escape(p.get("url", ""))
        shop = escape(p.get("shop_name", ""))
        review_avg = p.get("review_average", 0.0)
        review_count = p.get("review_count", 0)
        buy_score = p.get("buy_score", "-")
        judgment = escape(str(p.get("judgment", "-")))
        note = escape(trend_notes.get(p.get("item_code", ""), ""))

        image_html = (
            f'<img src="{image_url}" alt="{name}" loading="lazy" '
            f'style="max-width:120px;height:auto;">'
            if image_url
            else ""
        )

        rows.append(
            "<tr>"
            f"<td>{image_html}</td>"
            f'<td><a href="{url}" target="_blank" rel="nofollow noopener">{name}</a>'
            f"<br><small>{note}</small></td>"
            f"<td>{price_text}<br><small>{shop}</small></td>"
            f"<td>★{review_avg:.1f}({review_count:,}件)</td>"
            f"<td>{buy_score} / 100<br><strong>{judgment}</strong></td>"
            "</tr>"
        )

    table_html = (
        '<table border="1" cellspacing="0" cellpadding="6" style="border-collapse:collapse;width:100%;">'
        "<thead><tr>"
        "<th>画像</th><th>商品名</th><th>価格</th><th>レビュー</th><th>買い時スコア</th>"
        "</tr></thead>"
        f"<tbody>{''.join(rows)}</tbody>"
        "</table>"
    )
    return table_html


def build_disclaimer_html(fetched_at_jst: str) -> str:
    """価格・在庫情報の取得日時の明記 + アフィリエイト開示文(景品表示法対応)。

    バリューコマース未提携(VC_AFFILIATE_ID未設定)の間は通常URLでのリンクのみのため、
    厳密には「アフィリエイトプログラムを利用しており」の一文はまだ事実と異なるが、
    景品表示法上の開示は「将来的に収益が発生しうる可能性のある記事」であることを
    早期から明示しておく方が安全側であるためこのまま出力する(実害なし)。
    """
    return (
        "<hr>"
        '<p style="font-size:0.85em;color:#666;">'
        f"※価格・レビュー件数等の情報は {escape(fetched_at_jst)} 時点でYahoo!ショッピングAPI経由により"
        "取得したものです。実際の価格・在庫状況は変動する場合があるため、購入前に必ず商品ページで"
        "ご確認ください。<br>"
        "本記事はアフィリエイトプログラム(バリューコマース等)の利用を予定しており、記事内リンクを"
        "経由して商品が購入された場合、当サイトが紹介料を受け取ることがあります。"
        "</p>"
    )


def build_credit_html() -> str:
    """Yahoo!デベロッパーネットワークのクレジット表示(義務表示)。

    出典・確認済み文言: angel/developer/tasks.md の
    「## 秘書によるクレジット表示文言の確認 [2026-07-13]」参照
    (https://developer.yahoo.co.jp/attribution/)。

    形式A(日本語テキストリンク)の公式HTMLソースをそのまま使用(改変禁止のため
    style属性・リンク先URL・文言は一切変更しないこと)。

    配置ルール(公式規定): 「サイトの下部」に1箇所あればよい。本関数はサイト全体
    フッター(はてなブログのデザイン設定側HTML、社長作業)への設置を主目的とするが、
    念のための二重化として記事本文末尾にも挿入できるよう関数化してある
    (developer/tasks.md記載の通り、二重設置自体は規約違反ではない)。
    """
    return (
        "\n<!-- Begin Yahoo! JAPAN Web Services Attribution Snippet -->\n"
        '<span style="margin:15px 15px 15px 15px">'
        '<a href="https://developer.yahoo.co.jp/sitemap/">Webサービス by Yahoo! JAPAN</a>'
        "</span>\n"
        "<!-- End Yahoo! JAPAN Web Services Attribution Snippet -->\n"
    )
