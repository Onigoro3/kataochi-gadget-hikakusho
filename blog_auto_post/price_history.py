"""価格推移データの蓄積・参照。

Yahoo!ショッピングAPIも過去の価格履歴を提供しないため、本スクリプトを実行するたびに
Supabase(sa_state, key="angel_price_history")へ商品コード単位で価格スナップショットを
追記していく。運用を重ねるほど「価格推移データ」という差別化要素の精度が上がって
いく設計。

Dragon(app/blog_auto_post/price_history.py)と完全に同一のロジック(移植のみ、無改修)。

2026-07-17: 従来はdata/price_history.jsonをGitHub Actionsがgit commitして永続化
していたが、push競合のリスクを避けるためSupabaseへ移行した
(sa_common.supabase_store参照)。
"""
from __future__ import annotations

from datetime import date
from typing import Any

from sa_common.supabase_store import get_state, set_state

STATE_KEY = "angel_price_history"


def load_history() -> dict[str, list[dict[str, Any]]]:
    return get_state(STATE_KEY, {})


def save_history(history: dict[str, list[dict[str, Any]]]) -> None:
    set_state(STATE_KEY, history)


def update_history(
    history: dict[str, list[dict[str, Any]]],
    products: list[dict[str, Any]],
    run_date: str | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """本日分の価格スナップショットを追記する(同日重複は追記しない)。"""
    today = run_date or date.today().isoformat()

    for p in products:
        code = p.get("item_code")
        price = p.get("price")
        if not code or not price:
            continue
        entries = history.setdefault(code, [])
        if entries and entries[-1]["date"] == today:
            entries[-1]["price"] = price  # 同日の再取得は上書き
        else:
            entries.append({"date": today, "price": price})
        # 直近12回分のみ保持(肥大化防止)
        history[code] = entries[-12:]

    return history


def trend_note(history: dict[str, list[dict[str, Any]]], item_code: str, current_price: int) -> str:
    """商品ごとの価格推移についての短い注記テキストを生成する。"""
    entries = history.get(item_code, [])
    if len(entries) < 2:
        return ""

    previous = entries[-2]["price"]
    if current_price < previous:
        diff = previous - current_price
        return f"前回計測({entries[-2]['date']})の¥{previous:,}から¥{diff:,}値下がりしています。"
    if current_price > previous:
        diff = current_price - previous
        return f"前回計測({entries[-2]['date']})の¥{previous:,}から¥{diff:,}値上がりしています。"
    return f"前回計測({entries[-2]['date']})から価格変動はありません。"
