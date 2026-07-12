"""バリューコマース アフィリエイトURL変換(Week 6以降の収益化フェーズ向け)。

現時点(2026-07-13)ではバリューコマースへのメディア登録・広告主審査が未着手のため、
`VC_AFFILIATE_ID` は環境変数未設定(空文字)で運用する。未設定の間は通常の商品URLの
ままリンクを張り、提携完了後にこの関数の中身を実際のリンク変換ロジックへ差し替える。

**要調査(ASP審査通過後に対応)**: バリューコマースの広告主(ビックカメラ/ノジマ/
エディオン等)ごとに発行される実際のアフィリエイトリンク形式(sid/pid付きリダイレクト
URLへの変換方法、diid等の必須パラメータ)は現時点では未確認。審査通過時に秘書へ
公式マニュアルの確認を依頼し、`to_affiliate_url()` の中身を実装する。
"""
from __future__ import annotations


def to_affiliate_url(raw_url: str, affiliate_id: str = "", affiliate_type: str = "vc") -> str:
    """商品URLをアフィリエイトURLへ変換する。

    `affiliate_id` が空文字の間(ASP未提携)は `raw_url` をそのまま返す。
    提携後は環境変数 `VC_AFFILIATE_ID` を設定するだけで、新規記事から自動的に
    アフィリエイトURL化される(過去記事の遡及更新は別途バッチが必要。developer/tasks.md参照)。
    """
    if not affiliate_id:
        return raw_url

    # TODO(Week6〜, ASP審査通過後): バリューコマースの実際のリンク変換ロジックに置き換える。
    # 現時点ではプレースホルダーとして raw_url をそのまま返す(誤ったURL形式を生成して
    # リンク切れ・機会損失を招くより、未実装のまま通常URLを使い続ける方が安全なため)。
    print(
        "[affiliate] 警告: VC_AFFILIATE_ID が設定されていますが、"
        "to_affiliate_url() は未実装のプレースホルダーです。通常URLのまま返却します。"
    )
    return raw_url
