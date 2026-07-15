"""はてなブログ AtomPub API連携(WSSE認証)。

公式仕様: https://help.hatena.ne.jp/entry/atompub
エンドポイント: https://blog.hatena.ne.jp/{hatena_id}/{blog_domain}/atom/entry

Dragon(app/blog_auto_post/hatena_client.py)と完全に同一のロジック(移植のみ、無改修。
はてなブログAPI自体はデータソース(楽天/Yahoo)に依存しないため、そのまま流用可能)。
"""
from __future__ import annotations

import base64
import hashlib
import os
import time
from datetime import datetime, timezone
from xml.sax.saxutils import escape

import requests

ATOM_NS = "http://www.w3.org/2005/Atom"
APP_NS = "http://www.w3.org/2007/app"


class HatenaAPIError(RuntimeError):
    pass


def _build_wsse_header(username: str, api_key: str) -> str:
    """WSSE(UsernameToken)認証ヘッダを組み立てる。

    PasswordDigest = Base64(SHA1(Nonce(raw bytes) + Created(string) + APIKey(string)))
    """
    created = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    nonce_raw = os.urandom(16)
    digest = hashlib.sha1(nonce_raw + created.encode("utf-8") + api_key.encode("utf-8")).digest()

    password_digest = base64.b64encode(digest).decode("utf-8")
    nonce_b64 = base64.b64encode(nonce_raw).decode("utf-8")

    return (
        f'UsernameToken Username="{username}", '
        f'PasswordDigest="{password_digest}", '
        f'Nonce="{nonce_b64}", '
        f'Created="{created}"'
    )


def _build_entry_xml(
    title: str,
    content_html: str,
    categories: list[str],
    author_name: str,
    draft: bool,
) -> str:
    category_xml = "".join(
        f'<category term="{escape(c)}" />' for c in categories if c
    )
    updated = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    return f"""<?xml version="1.0" encoding="utf-8"?>
<entry xmlns="{ATOM_NS}" xmlns:app="{APP_NS}">
  <title>{escape(title)}</title>
  <author><name>{escape(author_name)}</name></author>
  <content type="text/html">{escape(content_html)}</content>
  <updated>{updated}</updated>
  {category_xml}
  <app:control>
    <app:draft>{"yes" if draft else "no"}</app:draft>
  </app:control>
</entry>"""


def post_entry(
    hatena_id: str,
    blog_domain: str,
    api_key: str,
    title: str,
    content_html: str,
    categories: list[str] | None = None,
    draft: bool = False,
    timeout: int = 30,
) -> dict:
    """はてなブログへ記事を投稿する。デフォルトは公開状態(draft=False)。

    Returns: {"status_code": int, "location": str | None, "raw": str}
    """
    endpoint = f"https://blog.hatena.ne.jp/{hatena_id}/{blog_domain}/atom/entry"
    xml_body = _build_entry_xml(
        title=title,
        content_html=content_html,
        categories=categories or [],
        author_name=hatena_id,
        draft=draft,
    )

    headers = {
        "Content-Type": "application/atom+xml;type=entry;charset=utf-8",
        "X-WSSE": _build_wsse_header(hatena_id, api_key),
    }

    try:
        resp = requests.post(
            endpoint, data=xml_body.encode("utf-8"), headers=headers, timeout=timeout
        )

        if resp.status_code == 429:
            # レート制限。少し待って1回だけリトライ(rakuten_client.pyと同様の設計)。
            time.sleep(3)
            resp = requests.post(
                endpoint, data=xml_body.encode("utf-8"), headers=headers, timeout=timeout
            )
    except requests.exceptions.RequestException as e:
        # タイムアウト・接続エラー等のネットワーク例外もHatenaAPIErrorとして統一する
        # (2026-07-15修正: 従来はここが未捕捉のためrequestsの生例外がそのまま呼び出し元へ
        # 漏れており、rakuten_client.pyの接続エラー処理と非対称だった)
        raise HatenaAPIError(f"はてなブログAPIへの接続に失敗しました: {e}") from e

    if resp.status_code not in (200, 201):
        raise HatenaAPIError(
            f"はてなブログ投稿失敗 status={resp.status_code} body={resp.text[:500]}"
        )

    return {
        "status_code": resp.status_code,
        "location": resp.headers.get("Location"),
        "raw": resp.text,
    }
