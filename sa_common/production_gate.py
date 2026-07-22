"""全社共通「量産ゲート」(2026-07-23社長承認、ceo/tasks.md 論点6)。

週次URL Inspection実測(dashboard/scripts/weekly_index_check.pyがSupabase
sa_state(key="index_rate_state")へ書き込むキャッシュ)を読み、自部署の
インデックス率が閾値(既定50%)未満の場合、新規記事のトピック選定を
「直近使用された記事型(article_type)と異なる型」に限定する。

Dragon(app/sa_common)・Angel(angel/app/sa_common)・Demon(demon/app/sa_common)・
Venus(venus/app/sa_common)に同一内容で複製配置する(sa_common配下の既存の
複製パターン=supabase_store.pyと同じ方針。各プロジェクトは他プロジェクトを
importせず自己完結させる)。

「10本積んでからインデックス率10%に気づく」(Demon実例)のような事故を、
コードレベルで機械的に防ぐことが目的。ただし候補が1件も無い場合(そもそも
article_typeの多様性がキューに無い部署等)は投稿ゼロ化を避けるため制限を
効かせず、従来通りの選定にフォールバックする。
"""
from __future__ import annotations

from typing import Any

from sa_common.supabase_store import get_state

INDEX_RATE_STATE_KEY = "index_rate_state"

# 量産ゲートが「直近の型」を判定する際に振り返る、使用済みトピックの件数
_RECENT_LOOKBACK = 5


def should_restrict_to_new_format(index_rate: float, threshold: float = 0.5) -> bool:
    """インデックス率が閾値未満なら True(=新規記事を既存と型の違う記事に限定すべき)。"""
    return index_rate < threshold


def load_department_index_rate(department_key: str) -> float | None:
    """Supabase(key="index_rate_state")から自部署分のインデックス率(0.0〜1.0)を読む。

    週次検査未実施・Supabase接続エラー・該当部署のデータが無い場合はいずれも
    Noneを返す(呼び出し側でゲートを効かせない=投稿を止めないフォールバック)。
    """
    try:
        data = get_state(INDEX_RATE_STATE_KEY, None)
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    entry = data.get(department_key)
    if not isinstance(entry, dict):
        return None
    rate = entry.get("index_rate")
    if not isinstance(rate, (int, float)):
        return None
    return float(rate)


def most_common_recent_article_type(all_topics: list[dict[str, Any]], lookback: int = _RECENT_LOOKBACK) -> str | None:
    """使用済みトピックのうち直近lookback件(used_at降順)で最頻のarticle_typeを返す。

    article_type未設定のトピックは"comparison"(既定の比較型)として扱う
    (Demonの`article_type`分岐と同じデフォルト、後方互換のため)。
    使用済みトピックが1件も無ければNoneを返す。
    """
    used = [t for t in all_topics if t.get("used_at")]
    used.sort(key=lambda t: t.get("used_at", ""), reverse=True)
    recent = used[:lookback]
    if not recent:
        return None

    counts: dict[str, int] = {}
    for t in recent:
        art_type = t.get("article_type", "comparison")
        counts[art_type] = counts.get(art_type, 0) + 1
    return max(counts.items(), key=lambda kv: kv[1])[0]


def filter_topics_by_gate(
    unused_topics: list[dict[str, Any]],
    all_topics: list[dict[str, Any]],
    index_rate: float | None,
    threshold: float = 0.5,
) -> list[dict[str, Any]]:
    """量産ゲートを適用したうえでの未使用トピック候補リストを返す。

    - index_rateがNone(週次検査未実施・取得失敗)の場合: ゲートを効かせず元のリストを返す
    - index_rate >= threshold の場合: ゲートを効かせず元のリストを返す(通常運用)
    - index_rate < threshold の場合: 直近使用された記事型と異なるarticle_typeの
      トピックのみに絞り込む。絞り込んだ結果が0件になる場合は「新規記事ゼロ」を
      避けるため制限をかけず元のリストへフォールバックする。
    """
    if index_rate is None or not should_restrict_to_new_format(index_rate, threshold):
        return unused_topics

    recent_type = most_common_recent_article_type(all_topics)
    if recent_type is None:
        return unused_topics

    filtered = [t for t in unused_topics if t.get("article_type", "comparison") != recent_type]
    return filtered if filtered else unused_topics
