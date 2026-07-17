"""Supabase上の汎用JSON状態ストア(sa_stateテーブル)への読み書き。

Dragon(app/sa_common/supabase_store.py)と完全に同一のロジック(移植のみ、無改修)。
Dragon/Angel/Demonは同一Supabaseプロジェクト(Secred-Abyss)のsa_stateテーブルを
共有するため、キー名の先頭に部署名を付けて衝突を避ける(例: "angel_topics")。

各Botのhistory/log/queueは元々「1ファイル=1JSONドキュメント」という構造で、
GitHub Actionsが実行後にgit commit&pushして永続化していた。この方式は複数の
ワークフローが同時にpushすると競合する(2026-07-16/17に実際に発生した
二重投稿・記録消失インシデント参照)。本モジュールはそれをkey-valueテーブルへの
読み書きに置き換える。1キー=1JSONドキュメントという形は維持するため、
呼び出し側(各Botのload/save関数)の中身のロジックは変更不要。

テーブル定義(Supabase側で作成済み、Dragon側で一度だけ作成した共有テーブル):
    create table sa_state (
      key text primary key,
      value jsonb not null,
      updated_at timestamptz not null default now()
    );

環境変数 SUPABASE_URL / SUPABASE_SECRET_KEY が必要(GitHub Secretsから供給)。
未設定の場合は黙って空データを返さず、明示的にSupabaseStoreErrorを送出する
(設定漏れによる「履歴が消えたように見える」事故を早期に検知するため)。
"""
from __future__ import annotations

import os
from typing import Any

import requests

_TIMEOUT_SECONDS = 15


class SupabaseStoreError(RuntimeError):
    pass


def _base_url() -> str:
    url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    if not url:
        raise SupabaseStoreError("環境変数 SUPABASE_URL が設定されていません")
    return url


def _headers() -> dict[str, str]:
    key = os.environ.get("SUPABASE_SECRET_KEY", "")
    if not key:
        raise SupabaseStoreError("環境変数 SUPABASE_SECRET_KEY が設定されていません")
    return {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }


def get_state(key: str, default: Any) -> Any:
    """指定キーのJSON値を取得する。行が存在しなければdefaultを返す。"""
    resp = requests.get(
        f"{_base_url()}/rest/v1/sa_state",
        headers=_headers(),
        params={"key": f"eq.{key}", "select": "value"},
        timeout=_TIMEOUT_SECONDS,
    )
    resp.raise_for_status()
    rows = resp.json()
    if not rows:
        return default
    return rows[0]["value"]


def set_state(key: str, value: Any) -> None:
    """指定キーにJSON値をupsert(無ければ作成・あれば上書き)する。"""
    resp = requests.post(
        f"{_base_url()}/rest/v1/sa_state",
        headers={**_headers(), "Prefer": "resolution=merge-duplicates"},
        json={"key": key, "value": value},
        timeout=_TIMEOUT_SECONDS,
    )
    resp.raise_for_status()
