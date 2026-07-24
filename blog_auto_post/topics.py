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


class TopicsExhaustedError(TopicQueueError):
    """未使用トピックがなく、自動リセットせず投稿をスキップすべき状態。

    2026-07-24社長判断(論点15③): 枯渇時に全件へ自動リセットして再利用すると、
    枯渇に気づかないまま既出テーマの記事が再生成され続ける恐れがあるため、
    自動リセットは廃止し、呼び出し元(main.py)が明示的にスキップできるよう
    この例外を送出する。
    """


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
    """未使用トピックをキュー順(配列の先頭)で1件選ぶ。

    編集会議がトピックを配列の先頭へ移動させることで次回投稿を制御できるよう、
    ランダム選択ではなく配列順を尊重する(旧: random.choice(unused))。

    2026-07-23社長承認: 全社共通「量産ゲート」(論点6)を適用する。index_rateが
    閾値未満なら、直近使用された記事型と異なるトピックのみに絞り込んでから
    配列先頭を選ぶ(sa_common.production_gate参照)。

    2026-07-24社長判断(論点15③): 全件使用済みになっても自動リセットはしない。
    `TopicsExhaustedError`を送出するので、呼び出し元(main.py)は編集会議での
    トピック追加が必要な状態として投稿をスキップすること。

    Args:
        index_rate: 週次URL Inspection実測の自部署インデックス率(0.0〜1.0)。
            Noneの場合(週次検査未実施・取得失敗)は量産ゲートを効かせない。

    Returns: (選ばれたトピック, 全トピックリスト(まだ使用済みマーク前))

    Raises:
        TopicsExhaustedError: 未使用トピックが1件も無い場合。
    """
    topics = load_topics()
    unused = [t for t in topics if not t.get("used", False)]

    if not unused:
        raise TopicsExhaustedError(
            f"未使用トピックがありません(key={STATE_KEY})。編集会議でのトピック追加が"
            "必要です(2026-07-24社長判断論点15③により、枯渇時の自動リセットは廃止)。"
        )

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
