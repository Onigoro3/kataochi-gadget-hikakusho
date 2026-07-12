"""独自スコアリング・買い時判定ロジック。

Yahoo!ショッピングAPIから取得した実データ(レビュー件数・平均評価・価格)のみから
機械的に算出する。LLMによる主観的な評価ではなく、決定論的な計算式にすることで
記事ごとの再現性・説明可能性を担保する(差別化ポイントの一つ)。

Dragon(app/blog_auto_post/scoring.py)と完全に同一のロジック(移植のみ、無改修)。
"""
from __future__ import annotations

from typing import Any

# スコア = レビュー平均(最大75点) + レビュー件数による人気度(最大15点)
#        + グループ内での価格の割安度(最大10点)
REVIEW_AVERAGE_WEIGHT = 15  # 5点満点 x 15 = 75点
REVIEW_COUNT_CAP = 500  # これ以上のレビュー件数は頭打ちで満点扱い
REVIEW_COUNT_WEIGHT = 15
PRICE_VALUE_WEIGHT = 10
PRICE_RATIO_CAP = 1.5  # 平均価格の1.5倍安い時点で価格スコア満点


def _judgment_label(score: float) -> str:
    if score >= 70:
        return "買い時"
    if score >= 50:
        return "妥当"
    return "様子見"


def compute_scores(products: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """各商品に buy_score(0-100) と judgment(買い時/妥当/様子見)を付与して返す。"""
    if not products:
        return products

    prices = [p["price"] for p in products if p.get("price")]
    avg_price = sum(prices) / len(prices) if prices else 0

    for p in products:
        review_average = p.get("review_average") or 0.0
        review_count = p.get("review_count") or 0
        price = p.get("price") or 0

        review_score = min(review_average, 5.0) * REVIEW_AVERAGE_WEIGHT
        popularity_score = (
            min(review_count, REVIEW_COUNT_CAP) / REVIEW_COUNT_CAP * REVIEW_COUNT_WEIGHT
        )

        price_score = 0.0
        if avg_price and price:
            ratio = avg_price / price  # 1より大きいほど平均より割安
            price_score = min(ratio, PRICE_RATIO_CAP) / PRICE_RATIO_CAP * PRICE_VALUE_WEIGHT

        total = round(review_score + popularity_score + price_score, 1)
        p["buy_score"] = total
        p["judgment"] = _judgment_label(total)

    return products
