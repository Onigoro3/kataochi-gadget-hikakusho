"""楽天市場API(商品検索API: IchibaItem/Search)連携。

公式仕様: https://webservice.rakuten.co.jp/documentation/ichiba-item-search
レスポンスは `{"Items": [{"Item": {...}}], ...}` の形式で返る。
本モジュールではこの実際のレスポンス構造に沿って商品情報を正規化する。

2026年2〜5月の楽天ウェブサービスAPIインフラ刷新により、旧エンドポイント
(app.rakuten.co.jp)は2026-05-14で完全停止し、新エンドポイント
(openapi.rakuten.co.jp)への移行が必須になった。新エンドポイントでは
`applicationId` に加えて `accessKey` の送信が必須になり、さらに
アプリ登録時の「許可されたWebサイト」ドメインと一致する `Origin` ヘッダーが
ないと403になる(参考: https://freefielder.jp/blog/2026/02/rakuten-api-issue.html)。

Dragon(app/blog_auto_post/rakuten_client.py)と完全に同一のロジック(移植のみ、無改修)。
2026-07-14、AngelをYahoo!ショッピングAPIから楽天へ切り替える際に移植。
"""
from __future__ import annotations

import time
from typing import Any

import requests

SEARCH_ENDPOINT = "https://openapi.rakuten.co.jp/ichibams/api/IchibaItem/Search/20220601"


class RakutenAPIError(RuntimeError):
    pass


def _resize_image_url(url: str, size: str = "600x600") -> str:
    """楽天の画像URLについている `_ex=WxH` サイズ指定を大きめのサイズへ差し替える。

    楽天アフィリエイト規約上「サイズ変更」は許可されている改変の範囲内。
    トリミング・文字入れ等は行わない。
    """
    if not url:
        return url
    if "_ex=" in url:
        base = url.split("?")[0]
        return f"{base}?_ex={size}"
    return url


def _normalize_item(raw: dict[str, Any]) -> dict[str, Any]:
    item = raw.get("Item", raw)
    medium_images = item.get("mediumImageUrls") or []
    image_url = ""
    if medium_images:
        # 各要素は {"imageUrl": "..."} の形式
        image_url = medium_images[0].get("imageUrl", "")
    image_url = _resize_image_url(image_url)

    # affiliateUrl はアフィリエイトID指定時のみ付与される。あれば優先して使う。
    page_url = item.get("affiliateUrl") or item.get("itemUrl", "")

    return {
        "item_code": item.get("itemCode", ""),
        "name": item.get("itemName", ""),
        "price": item.get("itemPrice"),
        "url": page_url,
        "image_url": image_url,
        "shop_name": item.get("shopName", ""),
        "review_count": item.get("reviewCount", 0) or 0,
        "review_average": item.get("reviewAverage", 0.0) or 0.0,
        "catchcopy": item.get("catchcopy", ""),
        "item_caption": item.get("itemCaption", ""),
    }


def search_items(
    query: str,
    app_id: str,
    access_key: str,
    origin_domain: str,
    affiliate_id: str = "",
    hits: int = 12,
    timeout: int = 15,
) -> list[dict[str, Any]]:
    """楽天市場商品検索APIを1クエリ分呼び出し、正規化した商品リストを返す。

    2026年の新API仕様により `accessKey` と、アプリ登録時に「許可されたWebサイト」
    へ登録したドメインと一致する `Origin` ヘッダーが必須。
    """
    params = {
        "format": "json",
        "keyword": query,
        "applicationId": app_id,
        "accessKey": access_key,
        "hits": min(hits, 30),
        "imageFlag": 1,  # 画像ありの商品に限定
        "sort": "-reviewCount",  # レビュー件数の多い順(実在感のある商品を優先)
    }
    if affiliate_id:
        params["affiliateId"] = affiliate_id

    origin = origin_domain if origin_domain.startswith("http") else f"https://{origin_domain}"
    headers = {"Origin": origin, "Referer": origin}

    try:
        resp = requests.get(SEARCH_ENDPOINT, params=params, headers=headers, timeout=timeout)

        if resp.status_code == 429:
            # レート制限。少し待って1回だけリトライ。
            time.sleep(2)
            resp = requests.get(SEARCH_ENDPOINT, params=params, headers=headers, timeout=timeout)
    except requests.exceptions.RequestException as e:
        raise RakutenAPIError(f"楽天APIへの接続に失敗しました query={query!r}: {e}") from e

    if resp.status_code != 200:
        raise RakutenAPIError(
            f"楽天API呼び出し失敗 status={resp.status_code} query={query!r} body={resp.text[:300]}"
        )

    data = resp.json()
    if "error" in data:
        raise RakutenAPIError(
            f"楽天APIエラー query={query!r} error={data.get('error')} "
            f"description={data.get('error_description')}"
        )

    items = data.get("Items", [])
    return [_normalize_item(raw) for raw in items]


def fetch_products_for_topic(
    search_queries: list[str],
    app_id: str,
    access_key: str,
    origin_domain: str,
    affiliate_id: str = "",
    max_items: int = 12,
    per_query_hits: int = 10,
) -> list[dict[str, Any]]:
    """トピックに紐づく複数の検索クエリを実行し、重複除去しつつ商品リストをまとめる。"""
    merged: dict[str, dict[str, Any]] = {}

    for i, query in enumerate(search_queries):
        try:
            items = search_items(
                query, app_id, access_key, origin_domain, affiliate_id, hits=per_query_hits
            )
        except RakutenAPIError as e:
            # 1クエリの失敗で全体を止めない(他のクエリで代替できる可能性があるため)
            print(f"[rakuten_client] 警告: クエリ失敗をスキップ: {e}")
            items = []

        for item in items:
            key = item["item_code"] or item["url"]
            if key and key not in merged and item.get("price"):
                merged[key] = item

        if i < len(search_queries) - 1:
            time.sleep(1)  # レート制限に配慮

    products = list(merged.values())
    # レビュー件数の多い順に並べ替えてから上限で切る
    products.sort(key=lambda p: p.get("review_count", 0), reverse=True)
    return products[:max_items]
