"""Pexels API連携(記事テーマに関連した実写画像の取得)。

`last_minute_hotel_navi/pexels_client.py`(Dragonリポジトリ)と全く同じ実装(2026-07-20、
Dragon/Angel/Demonへの横展開の一環)。3ブログは別々のGitHubリポジトリのため、共有パッケージ化は
せず各リポジトリへ複製配置している(`sa_common/`が各リポジトリに複製されているのと同じ既存の
慣習を踏襲)。

商用利用可・クレジット表記は必須ではない(ただしPexels側の推奨に従い、挿入する各画像に
小さくクレジット表記を添える)。無料枠は1時間200件/月20,000件で、本Botの利用頻度
(1日1記事、1記事あたり画像1〜2枚程度の検索)であれば十分に収まる想定。PEXELS_API_KEYは
Dragon/Angel/Demonの3ブログで同一アカウントを共有する設計(社長方針)。

取得失敗時は例外を外へ伝播させず`None`を返す(1枚分の画像が取れなくても記事生成全体を
止めないため)。
"""
from __future__ import annotations

from typing import Any

import requests

SEARCH_ENDPOINT = "https://api.pexels.com/v1/search"


def search_photo(query: str, api_key: str, timeout: int = 10) -> dict[str, Any] | None:
    """キーワードで1枚検索し、画像URL・撮影者情報を返す。

    見つからない場合・APIエラー時・ネットワーク例外時はすべてNoneを返す
    (呼び出し側は「この箇所には画像を付けない」というだけで処理を継続できる)。
    """
    headers = {"Authorization": api_key}
    params = {
        "query": query,
        "per_page": 1,
        "orientation": "landscape",
        "size": "medium",
    }

    try:
        resp = requests.get(SEARCH_ENDPOINT, headers=headers, params=params, timeout=timeout)
    except requests.exceptions.RequestException:
        return None

    if resp.status_code != 200:
        return None

    try:
        data = resp.json()
    except ValueError:
        return None

    photos = data.get("photos") or []
    if not photos:
        return None

    photo = photos[0]
    src = photo.get("src") or {}
    image_url = src.get("large") or src.get("medium") or src.get("original")
    if not image_url:
        return None

    return {
        "image_url": image_url,
        "photographer": photo.get("photographer", ""),
        "photographer_url": photo.get("photographer_url", ""),
        "pexels_url": photo.get("url", "https://www.pexels.com"),
    }
