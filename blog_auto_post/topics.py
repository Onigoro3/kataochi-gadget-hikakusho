"""トピックキュー管理。

Supabase(sa_state, key="angel_topics")を読み書きし、未使用トピックを1件選んで
使用済みにマークする。全トピックを使い切った場合は自動的に全件を未使用へ
リセットして再利用する(トピック数が限られるPoCのため。将来的にはトピック追加
or 動的生成で拡張する拡張ポイント)。

Dragon(app/blog_auto_post/topics.py)と完全に同一のロジック(移植のみ、無改修)。
トピックの中身(旧data/topics.json)のみAngel独自(型落ちガジェット)。

2026-07-17: 従来はdata/topics.jsonをGitHub Actionsがgit commitして永続化していたが、
他ワークフローの自動commitや手動pushとの競合(non-fast-forward)で記録が失われる
事故が発生したため、Supabaseへ移行した(sa_common.supabase_store参照)。
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sa_common.production_gate import filter_topics_by_gate
from sa_common.supabase_store import get_state, set_state

STATE_KEY = "angel_topics"

# 【2026-07-23社長承認・ceo/tasks.md 論点4】Angelは「商材カテゴリ競合度仮説」の
# 対照群として現状維持(寄せない)に割り当てられた。Dragon/Venusのようなprice_tier
# 優先並べ替えはAngelには追加しない(意図的な無変更)。


class TopicQueueError(RuntimeError):
    pass


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def load_topics() -> list[dict[str, Any]]:
    data = get_state(STATE_KEY, None)
    if data is None:
        raise TopicQueueError(f"Supabaseにトピックデータが見つかりません(key={STATE_KEY})")
    if not isinstance(data, list):
        raise TopicQueueError("topicsデータの形式が不正です(トップレベルはリストである必要があります)")
    return data


def save_topics(topics: list[dict[str, Any]]) -> None:
    set_state(STATE_KEY, topics)


def pick_topic(index_rate: float | None = None) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """未使用トピックをキュー順(配列の先頭)で1件選ぶ。全件使用済みなら全件リセットしてから選ぶ。

    編集会議がトピックを配列の先頭へ移動させることで次回投稿を制御できるよう、
    ランダム選択ではなく配列順を尊重する(旧: random.choice(unused))。

    2026-07-23社長承認: 全社共通「量産ゲート」(論点6)を適用する。index_rateが
    閾値未満なら、直近使用された記事型と異なるトピックのみに絞り込んでから
    配列先頭を選ぶ(sa_common.production_gate参照)。

    Args:
        index_rate: 週次URL Inspection実測の自部署インデックス率(0.0〜1.0)。
            Noneの場合(週次検査未実施・取得失敗)は量産ゲートを効かせない。

    Returns: (選ばれたトピック, 全トピックリスト(まだ使用済みマーク前))
    """
    topics = load_topics()
    unused = [t for t in topics if not t.get("used", False)]

    if not unused:
        # 全て使い切った場合は再利用のため全件リセット(使用回数はカウントアップして残す)
        for t in topics:
            t["used"] = False
            t["used_at"] = None
        unused = topics

    unused = filter_topics_by_gate(unused, topics, index_rate)

    chosen = unused[0]
    return chosen, topics


def mark_used(topic_id: str, topics: list[dict[str, Any]]) -> None:
    for t in topics:
        if t.get("id") == topic_id:
            t["used"] = True
            t["used_at"] = _now_iso()
            t["use_count"] = t.get("use_count", 0) + 1
            break
    else:
        raise TopicQueueError(f"トピックID {topic_id} が見つかりません")
    save_topics(topics)
