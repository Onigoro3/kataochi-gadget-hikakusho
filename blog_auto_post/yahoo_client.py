"""Yahoo!ショッピングAPI(商品検索API v3 itemSearch)連携。

公式ドキュメント: https://developer.yahoo.co.jp/webapi/shopping/v3/itemsearch.html

2026-07-13 実機検証済み(Client ID取得後、`appid=<client_id>&query=...` で実際に
200応答・商品データを取得できることを確認)。エンドポイントURL・主要フィールド名は
下記の通り実レスポンスと一致することを確認済み。

実レスポンス構造(itemSearch v3、実機確認済み):
    {
        "totalResultsAvailable": int,
        "totalResultsReturned": int,
        "firstResultsPosition": int,   # 実機確認: "firstResultPosition"ではなく"firstResultsPosition"(末尾s)
        "request": {"query": "..."},
        "hits": [
            {
                "name": "...",
                "description": "...",
                "headLine": "...",
                "url": "...",
                "code": "...",              # 商品コード(楽天のitemCodeに相当)
                "image": {"medium": "...", "small": "..."},
                "price": 12345,
                "review": {"rate": 4.5, "count": 100, "url": "..."},
                "seller": {"sellerId": "...", "name": "...", "url": "...", "review": {...}},
                    # 実機確認: 当初想定していた"store"キーは存在せず、正しくは"seller"
                ...
            },
            ...
        ],
    }

レート制限(秘書調査済み):
    - 上限: 50,000リクエスト/日
    - ハードリミット: 1クエリ秒(バーストするとエラーになりうる)
    本モジュールの `_RateLimiter` は「直前の呼び出しから最低1.1秒空ける」ことを実際に
    計測して保証する(Dragon版rakuten_client.pyの「クエリ間にsleep(1)を挟む」よりも
    一段階厳密な実装)。
"""
from __future__ import annotations

import time
from typing import Any

import requests

# 要検証: 実際のエンドポイントURL。公式ドキュメント確認後に修正すること。
SEARCH_ENDPOINT = "https://shopping.yahooapis.jp/ShoppingWebService/V3/itemSearch"

MIN_INTERVAL_SECONDS = 1.1  # 「1クエリ秒」制限に対し余裕を持たせた最小呼び出し間隔


class YahooAPIError(RuntimeError):
    pass


class _RateLimiter:
    """直近の呼び出し時刻を記録し、次回呼び出し前に必要な分だけsleepする簡易リミッタ。

    トークンバケットと呼ぶには単純だが、「直近1回からの経過時間」だけを見て
    不足分を待つ方式で「1クエリ秒」制限を確実に順守する。プロセス内で使い回す
    想定のモジュールレベルシングルトンとして `_rate_limiter` を用意する。
    """

    def __init__(self, min_interval: float = MIN_INTERVAL_SECONDS):
        self._min_interval = min_interval
        self._last_call_at: float | None = None
        self.request_count = 0  # 将来の日次上限監視用(README参照)

    def wait(self) -> None:
        if self._last_call_at is not None:
            elapsed = time.monotonic() - self._last_call_at
            remaining = self._min_interval - elapsed
            if remaining > 0:
                time.sleep(remaining)
        self._last_call_at = time.monotonic()
        self.request_count += 1


_rate_limiter = _RateLimiter()


def _resize_image_url(url: str) -> str:
    """Yahoo!ショッピングの画像URLはサイズ違いが `image.medium` として提供されるため、
    楽天版のようなクエリパラメータでのリサイズ加工は不要(実機確認済み)。
    """
    return url


def _normalize_item(raw: dict[str, Any]) -> dict[str, Any]:
    """Yahoo APIレスポンスの1商品を、Dragon(rakuten_client.py)と同一の内部スキーマへ正規化する。

    table_builder.py / scoring.py / price_history.py をDragonとほぼ無改修で共用できるよう、
    キー名は意図的に楽天版に揃えている。

    2026-07-13 実機検証で修正: 店舗情報は当初想定の"store"キーではなく"seller"キーで
    返ってくることを確認したため修正済み。
    """
    image = raw.get("image") or {}
    review = raw.get("review") or {}
    seller = raw.get("seller") or {}

    return {
        "item_code": raw.get("code", ""),
        "name": raw.get("name", ""),
        "price": raw.get("price"),
        "url": raw.get("url", ""),  # アフィリエイトURL化は affiliate.py 側で行う
        "image_url": _resize_image_url(image.get("medium", "") or image.get("small", "")),
        "shop_name": seller.get("name", ""),
        "review_count": review.get("count", 0) or 0,
        "review_average": review.get("rate", 0.0) or 0.0,
        "catchcopy": raw.get("headLine", ""),
        "item_caption": raw.get("description", ""),
    }


def search_items(
    query: str,
    client_id: str,
    affiliate_type: str = "",
    affiliate_id: str = "",
    results: int = 12,
    timeout: int = 15,
) -> list[dict[str, Any]]:
    """Yahoo!ショッピングAPI itemSearchを1クエリ分呼び出し、正規化した商品リストを返す。

    呼び出し前に `_rate_limiter.wait()` で「1クエリ秒」制限を順守する。
    429 / レート超過相当のエラー時は2秒待って1回だけ再試行し、それでも失敗すれば
    当該クエリはスキップして処理を継続する(Dragon方式を踏襲)。
    """
    _rate_limiter.wait()

    params: dict[str, Any] = {
        "appid": client_id,  # Yahoo!デベロッパーネットワークで発行される「Client ID」
        "query": query,
        "results": min(results, 30),  # 実機確認: results=30まで指定通りhitsが返ることを確認済み
        "sort": "-review_count",  # レビュー件数の多い順(実機確認: パラメータ名・降順指定とも正常動作)
        "image_size": 300,
        "in_stock": "true",
    }
    # バリューコマース提携後、affiliate_id設定時のみアフィリエイトパラメータを付与する想定
    # (VC_AFFILIATE_ID未設定運用の現段階ではこの分岐は未通過・未検証のまま。
    # Yahoo!ショッピングAPI自体がアフィリエイトURLを返す仕組みなのか、バリューコマース側の
    # リンク変換が別途必要なのかは affiliate.py 側の要調査事項として引き続き切り出しておく)
    if affiliate_type and affiliate_id:
        params["affiliate_type"] = affiliate_type
        params["affiliate_id"] = affiliate_id

    try:
        resp = requests.get(SEARCH_ENDPOINT, params=params, timeout=timeout)

        if resp.status_code == 429:
            time.sleep(2)
            resp = requests.get(SEARCH_ENDPOINT, params=params, timeout=timeout)
    except requests.exceptions.RequestException as e:
        raise YahooAPIError(f"Yahoo!ショッピングAPIへの接続に失敗しました query={query!r}: {e}") from e

    if resp.status_code != 200:
        raise YahooAPIError(
            f"Yahoo!ショッピングAPI呼び出し失敗 status={resp.status_code} "
            f"query={query!r} body={resp.text[:300]}"
        )

    data = resp.json()
    if "Error" in data or "error" in data:
        raise YahooAPIError(
            f"Yahoo!ショッピングAPIエラー query={query!r} response={str(data)[:300]}"
        )

    hits = data.get("hits", [])
    return [_normalize_item(raw) for raw in hits]


def fetch_products_for_topic(
    search_queries: list[str],
    client_id: str,
    affiliate_type: str = "",
    affiliate_id: str = "",
    max_items: int = 12,
    per_query_results: int = 10,
) -> list[dict[str, Any]]:
    """トピックに紐づく複数の検索クエリを実行し、重複除去しつつ商品リストをまとめる。

    Dragon(rakuten_client.fetch_products_for_topic)と同一の設計。クエリ間の待機は
    `search_items()` 呼び出し時に `_rate_limiter.wait()` が保証するため、ここでの
    明示的な `time.sleep()` は不要(Dragon版との違い)。
    """
    merged: dict[str, dict[str, Any]] = {}

    for query in search_queries:
        try:
            items = search_items(
                query,
                client_id,
                affiliate_type=affiliate_type,
                affiliate_id=affiliate_id,
                results=per_query_results,
            )
        except YahooAPIError as e:
            # 1クエリの失敗で全体を止めない(他のクエリで代替できる可能性があるため)
            print(f"[yahoo_client] 警告: クエリ失敗をスキップ: {e}")
            items = []

        for item in items:
            key = item["item_code"] or item["url"]
            if key and key not in merged and item.get("price"):
                merged[key] = item

    products = list(merged.values())
    products.sort(key=lambda p: p.get("review_count", 0), reverse=True)

    print(
        f"[yahoo_client] 本日推定リクエスト数: {_rate_limiter.request_count}/50000"
        "(日次上限に対する目安。将来の複数記事・再取得バッチ追加時の安全弁)"
    )

    return products[:max_items]
