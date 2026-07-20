"""比較表(HTML)の組み立て。

価格・型番・スペック等の実データはLLMに生成させず、楽天APIから取得した値を
そのままコードで整形する(ハルシネーション防止・数値の正確性担保のため)。
LLMにはこの完成済みHTMLブロックを記事内の適切な位置に挿入させる形で連携する。

2026-07-14、データソースをYahoo!ショッピングAPIから楽天市場APIへ切り替えたのに伴い、
Dragon(app/blog_auto_post/table_builder.py)と完全に同一の実装へ揃えた(Yahoo!クレジット
表示・楽天補助リンクは不要になったため撤去)。
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
        note_html = f"<br><small>{note}</small>" if note else ""

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
            f"{note_html}</td>"
            f"<td>{price_text}<br><small>{shop}</small></td>"
            f"<td>★{review_avg:.1f}({review_count:,}件)</td>"
            f"<td>{buy_score} / 100<br><strong>{judgment}</strong></td>"
            "</tr>"
        )

    table_html = (
        # 【2026-07-20修正】スマホ幅で全列が無理やり圧縮され、商品名セルが1文字ずつ
        # 改行される問題が実機で見つかった。横スクロール可能なdivで囲み、tableに
        # min-widthを設定することで、狭い画面では列を圧縮する代わりに横スクロールさせる
        # (Dragon/Demon/hotel_naviと共通の修正)。
        '<div style="overflow-x:auto;-webkit-overflow-scrolling:touch;">'
        '<table border="1" cellspacing="0" cellpadding="6" '
        'style="border-collapse:collapse;width:100%;min-width:640px;">'
        "<thead><tr>"
        "<th>画像</th><th>商品名</th><th>価格</th><th>レビュー</th><th>買い時スコア</th>"
        "</tr></thead>"
        f"<tbody>{''.join(rows)}</tbody>"
        "</table>"
        "</div>"
    )
    return table_html


def build_disclaimer_html(fetched_at_jst: str) -> str:
    """価格・在庫情報の取得日時の明記 + アフィリエイト開示文(景品表示法対応)。"""
    return (
        "<hr>"
        '<p style="font-size:0.85em;color:#666;">'
        f"※価格・レビュー件数等の情報は {escape(fetched_at_jst)} 時点で楽天市場API経由により取得したものです。"
        "実際の価格・在庫状況は変動する場合があるため、購入前に必ず商品ページでご確認ください。<br>"
        "本記事は楽天アフィリエイトプログラムを利用しており、記事内リンクを経由して商品が購入された場合、"
        "当サイトが紹介料を受け取ることがあります。"
        "</p>"
    )
