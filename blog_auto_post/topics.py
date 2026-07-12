"""トピックキュー管理。

data/topics.json を読み書きし、未使用トピックを1件選んで使用済みにマークする。
全トピックを使い切った場合は自動的に全件を未使用へリセットして再利用する
(トピック数が限られるPoCのため。将来的にはトピック追加 or 動的生成で拡張する拡張ポイント)。

Dragon(app/blog_auto_post/topics.py)と完全に同一のロジック(移植のみ、無改修)。
トピックの中身(data/topics.json)のみAngel独自(型落ちガジェット)。
"""
from __future__ import annotations

import json
import random
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_TOPICS_PATH = Path(__file__).resolve().parent.parent / "data" / "topics.json"


class TopicQueueError(RuntimeError):
    pass


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def load_topics(path: Path = DEFAULT_TOPICS_PATH) -> list[dict[str, Any]]:
    if not path.exists():
        raise TopicQueueError(f"トピックファイルが見つかりません: {path}")
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise TopicQueueError("topics.json の形式が不正です(トップレベルはリストである必要があります)")
    return data


def save_topics(topics: list[dict[str, Any]], path: Path = DEFAULT_TOPICS_PATH) -> None:
    with path.open("w", encoding="utf-8") as f:
        json.dump(topics, f, ensure_ascii=False, indent=2)
        f.write("\n")


def pick_topic(path: Path = DEFAULT_TOPICS_PATH) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """未使用トピックをランダムに1件選ぶ。全件使用済みなら全件リセットしてから選ぶ。

    Returns: (選ばれたトピック, 全トピックリスト(まだ使用済みマーク前))
    """
    topics = load_topics(path)
    unused = [t for t in topics if not t.get("used", False)]

    if not unused:
        # 全て使い切った場合は再利用のため全件リセット(使用回数はカウントアップして残す)
        for t in topics:
            t["used"] = False
            t["used_at"] = None
        unused = topics

    chosen = random.choice(unused)
    return chosen, topics


def mark_used(topic_id: str, topics: list[dict[str, Any]], path: Path = DEFAULT_TOPICS_PATH) -> None:
    for t in topics:
        if t.get("id") == topic_id:
            t["used"] = True
            t["used_at"] = _now_iso()
            t["use_count"] = t.get("use_count", 0) + 1
            break
    else:
        raise TopicQueueError(f"トピックID {topic_id} が見つかりません")
    save_topics(topics, path)
