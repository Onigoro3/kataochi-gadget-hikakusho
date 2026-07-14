"""環境変数からの設定読み込み。

認証情報・秘密情報はすべてここを経由して環境変数から取得する。
コード中にAPIキー等を直接書き込むことは禁止(README参照)。

2026-07-14、社長判断によりデータソースをYahoo!ショッピングAPIから楽天市場API
(Dragonと同一)へ切り替え。DragonとAngelが同じ楽天データで直接対決する構成になった
(差別化はトピックの切り口=白物家電 vs デジタルガジェットで担保)。
"""
from __future__ import annotations

import os
from dataclasses import dataclass

# ローカル実行時は .env を読み込む(GitHub Actionsではリポジトリ Secrets が
# 環境変数として直接注入されるため python-dotenv は無くても動作する)
try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # pragma: no cover - dotenv未インストールでも動作継続
    pass


class ConfigError(RuntimeError):
    """必須環境変数が不足している場合に送出する例外。"""


@dataclass(frozen=True)
class Settings:
    anthropic_api_key: str
    claude_model: str

    hatena_id: str
    hatena_blog_domain: str
    hatena_api_key: str

    rakuten_app_id: str
    rakuten_access_key: str
    rakuten_affiliate_id: str


REQUIRED_ENV_VARS = [
    "ANTHROPIC_API_KEY",
    "HATENA_ID",
    "HATENA_BLOG_DOMAIN",
    "HATENA_API_KEY",
    "RAKUTEN_APP_ID",
    "RAKUTEN_ACCESS_KEY",
    "RAKUTEN_AFFILIATE_ID",
]


def load_settings() -> Settings:
    """環境変数からSettingsを組み立てる。不足があればConfigErrorを送出する。"""
    missing = [name for name in REQUIRED_ENV_VARS if not os.environ.get(name)]
    if missing:
        raise ConfigError(
            "以下の環境変数が設定されていません: "
            + ", ".join(missing)
            + " (.env または GitHub Secrets を確認してください。詳細は app/README.md 参照)"
        )

    return Settings(
        anthropic_api_key=os.environ["ANTHROPIC_API_KEY"],
        claude_model=os.environ.get("CLAUDE_MODEL", "claude-sonnet-5"),
        hatena_id=os.environ["HATENA_ID"],
        hatena_blog_domain=os.environ["HATENA_BLOG_DOMAIN"],
        hatena_api_key=os.environ["HATENA_API_KEY"],
        rakuten_app_id=os.environ["RAKUTEN_APP_ID"],
        rakuten_access_key=os.environ["RAKUTEN_ACCESS_KEY"],
        rakuten_affiliate_id=os.environ["RAKUTEN_AFFILIATE_ID"],
    )
