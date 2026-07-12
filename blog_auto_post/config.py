"""環境変数からの設定読み込み。

認証情報・秘密情報はすべてここを経由して環境変数から取得する。
コード中にAPIキー等を直接書き込むことは禁止(README参照)。

Dragon(app/blog_auto_post/config.py)とほぼ同一構造だが、データソースが
楽天ウェブサービスではなくYahoo!ショッピングAPIである点、およびアフィリエイトIDが
バリューコマース経由(VC_AFFILIATE_ID、Week2以降のASP審査通過まで空文字運用)である点が異なる。
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

    yahoo_client_id: str
    vc_affiliate_id: str  # バリューコマース提携前は空文字(通常URLのまま運用)


# VC_AFFILIATE_ID は提携前は空文字運用のため必須変数には含めない(README参照)。
REQUIRED_ENV_VARS = [
    "ANTHROPIC_API_KEY",
    "HATENA_ID",
    "HATENA_BLOG_DOMAIN",
    "HATENA_API_KEY",
    "YAHOO_CLIENT_ID",
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
        yahoo_client_id=os.environ["YAHOO_CLIENT_ID"],
        vc_affiliate_id=os.environ.get("VC_AFFILIATE_ID", ""),
    )
