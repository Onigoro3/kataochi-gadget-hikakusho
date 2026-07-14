"""価格推移データの蓄積・参照。

Yahoo!ショッピングAPIも過去の価格履歴を提供しないため、本スクリプトを実行するたびに
data/price_history.json へ商品コード単位で価格スナップショットを追記していく。
GitHub Actions側でこのファイルをコミットして永続化することで、運用を重ねるほど
「価格推移データ」という差別化要素の精度が上がっていく設計。

Dragon(app/blog_auto_post/price_history.py)と完全に同一のロジック(移植のみ、無改修)。
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

DEFAULT_HISTORY_PATH = Path(__file__).resolve().parent.parent / "data" / "price_history.json"


def load_history(path: Path = DEFAULT_HISTORY_PATH) -> dict[str, list[dict[str, Any]]]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_history(history: dict[str, list[dict[str, Any]]], path: Path = DEFAULT_HISTORY_PATH) -> None:
    with path.open("w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)
        f.write("\n")


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
