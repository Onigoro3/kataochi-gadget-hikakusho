"""完全自動投稿ブログ「型落ちガジェット比較所」 メイン実行スクリプト。

フロー: トピック選択 -> Yahoo!ショッピングAPI商品データ取得 -> 独自スコアリング
        -> Claude記事生成(アウトライン/本文/タイトル/自己レビュー)
        -> 比較表HTML + クレジット表示 + 免責文言の組み込み -> はてなブログへ公開投稿
        -> トピック/価格履歴を保存

実行方法:
    python main.py

必要な環境変数は README.md 参照(.env または GitHub Secrets から供給)。

Dragon(app/main.py, 型落ち家電ラボ)とほぼ同一のフロー構成。データソースが
Yahoo!ショッピングAPIである点、比較表の直後にクレジット表示(Yahoo!デベロッパー
ネットワーク規定)を挿入する点が異なる。

拡張ポイント(将来対応時にコメントを参照):
- エラー通知: 現状はログ出力のみ。Discord Webhook等を追加する場合は
  `notify_failure()` を実装して except節から呼び出す形にする。
"""
from __future__ import annotations

import os
import sys
import traceback
from datetime import datetime, timedelta, timezone

from blog_auto_post import price_history, topics
from blog_auto_post.affiliate import to_affiliate_url
from blog_auto_post.article_pipeline import ArticlePipeline
from blog_auto_post.config import ConfigError, load_settings
from blog_auto_post.hatena_client import HatenaAPIError, post_entry
from blog_auto_post.scoring import compute_scores
from blog_auto_post.table_builder import (
    PRODUCT_TABLE_PLACEHOLDER,
    build_comparison_table_html,
    build_credit_html,
    build_disclaimer_html,
)
from blog_auto_post.yahoo_client import YahooAPIError, fetch_products_for_topic

JST = timezone(timedelta(hours=9))


def notify_failure(stage: str, error: Exception) -> None:
    """失敗時の通知処理。

    現状はGitHub Actionsのログに出力するのみ(要件通りPoCではこれで十分)。
    拡張ポイント: ここでDiscord Webhook(requests.post)等を呼び出せば
    実行失敗を即座に検知できるようになる。
    """
    print(f"::error::[{stage}] 失敗しました: {error}", file=sys.stderr)
    traceback.print_exc()


def main() -> int:
    try:
        settings = load_settings()
    except ConfigError as e:
        notify_failure("config", e)
        return 1

    # 1. トピック選択 ----------------------------------------------------
    try:
        topic, all_topics = topics.pick_topic()
        print(f"[main] 選定トピック: {topic['title']} (id={topic['id']})")
    except Exception as e:
        notify_failure("topic_selection", e)
        return 1

    # 2. Yahoo!ショッピングAPI商品データ取得 --------------------------------
    try:
        products = fetch_products_for_topic(
            search_queries=topic["search_queries"],
            client_id=settings.yahoo_client_id,
            affiliate_type="vc" if settings.vc_affiliate_id else "",
            affiliate_id=settings.vc_affiliate_id,
        )
        if not products:
            raise YahooAPIError("商品データが1件も取得できませんでした")
        # バリューコマース提携後、アフィリエイトURLへ変換(未提携の間はraw_urlのまま)
        for p in products:
            p["url"] = to_affiliate_url(p["url"], affiliate_id=settings.vc_affiliate_id)
        print(f"[main] Yahoo!ショッピングAPIから商品 {len(products)} 件取得")
    except Exception as e:  # YahooAPIError含む予期せぬ例外も安全に捕捉する
        notify_failure("yahoo_fetch", e)
        return 1

    # 3. 独自スコアリング + 価格履歴更新 -----------------------------------
    products = compute_scores(products)
    history = price_history.load_history()
    trend_notes = {
        p["item_code"]: price_history.trend_note(history, p["item_code"], p["price"])
        for p in products
        if p.get("item_code")
    }
    history = price_history.update_history(history, products)

    # 4. Claude記事生成 ----------------------------------------------------
    try:
        pipeline = ArticlePipeline(api_key=settings.anthropic_api_key, model=settings.claude_model)
        draft = pipeline.run(topic["title"], topic["category"], products)
        print(f"[main] 記事生成完了: title={draft.title!r}")
        print(f"[main] 自己レビューメモ: {draft.review_notes}")
    except Exception as e:
        notify_failure("article_generation", e)
        return 1

    # 5. 比較表・クレジット表示・免責文言の組み込み ---------------------------
    fetched_at_jst = datetime.now(JST).strftime("%Y-%m-%d %H:%M JST")
    table_html = build_comparison_table_html(products, trend_notes)
    credit_html = build_credit_html()
    disclaimer_html = build_disclaimer_html(fetched_at_jst)

    # 比較表の直後にクレジット表示、その後に免責文言(developer/tasks.md記載の順序)
    final_html = draft.body_html.replace(
        PRODUCT_TABLE_PLACEHOLDER, table_html + credit_html
    )
    if draft.meta_description:
        final_html = (
            f'<p style="display:none">{draft.meta_description}</p>\n' + final_html
        )
    final_html += disclaimer_html

    # 6. はてなブログへ投稿(完全自動公開) -----------------------------------
    # 環境変数 ANGEL_DRY_RUN=true (または 1/yes) が設定されている場合のみ、実際の投稿を
    # 行わず投稿予定内容を標準出力に表示するだけに留める(2026-07-13 実機検証時に導入)。
    # 未設定(デフォルト)の場合は通常通り post_entry() を実行して本番公開する。
    dry_run = os.environ.get("ANGEL_DRY_RUN", "").strip().lower() in ("1", "true", "yes")
    if dry_run:
        dry_run_url = (
            f"https://{settings.hatena_blog_domain}/entry/"
            f"{datetime.now(JST).strftime('%Y/%m/%d/%H%M%S')}"
        )
        print("[main] === ANGEL_DRY_RUN=true: post_entry() は実行していません(実際には投稿されません) ===")
        print(f"[main] 投稿予定タイトル: {draft.title!r}")
        print(f"[main] 投稿予定本文冒頭(200文字): {final_html[:200]!r}")
        print(f"[main] 投稿予定URL(推定・実際の値は投稿後に確定): {dry_run_url}")
        print(f"[main] 投稿予定カテゴリ: {[topic['category'], '型落ちガジェット比較']}")
    else:
        try:
            result = post_entry(
                hatena_id=settings.hatena_id,
                blog_domain=settings.hatena_blog_domain,
                api_key=settings.hatena_api_key,
                title=draft.title,
                content_html=final_html,
                categories=[topic["category"], "型落ちガジェット比較"],
                draft=False,  # 社長方針: 最初から完全自動公開
            )
            print(f"[main] はてなブログ投稿成功: {result.get('location')}")
        except Exception as e:  # HatenaAPIError含む予期せぬ例外も安全に捕捉する
            notify_failure("hatena_post", e)
            return 1

    # 7. トピック使用済みマーク・価格履歴の保存 -------------------------------
    topics.mark_used(topic["id"], all_topics)
    price_history.save_history(history)
    print("[main] トピック使用済みマーク・価格履歴保存 完了")

    return 0


if __name__ == "__main__":
    sys.exit(main())
