"""完全自動投稿ブログ「型落ちガジェット比較所」 メイン実行スクリプト。

フロー: トピック選択 -> 楽天API商品データ取得 -> 独自スコアリング
        -> Claude記事生成(アウトライン/本文/タイトル/自己レビュー)
        -> 比較表HTML + 免責文言の組み込み -> はてなブログへ公開投稿
        -> トピック/価格履歴を保存

実行方法:
    python main.py

必要な環境変数は README.md 参照(.env または GitHub Secrets から供給)。

Dragon(app/main.py, 型落ち家電ラボ)と同一のデータソース(楽天API)を使う構成
(2026-07-14、社長判断でYahoo!ショッピングAPIから切り替え)。DragonとAngelは同じ
楽天データで直接対決し、差別化はトピックの切り口(白物家電 vs デジタルガジェット)で担保する。

拡張ポイント(将来対応時にコメントを参照):
- エラー通知: 現状はログ出力のみ。Discord Webhook等を追加する場合は
  `notify_failure()` を実装して except節から呼び出す形にする。

ドライラン: 環境変数 `ANGEL_DRY_RUN=true` を設定すると、はてなブログへの実投稿・
topics.json/price_history.jsonへの書き込みの両方を行わず、投稿予定内容を標準出力に
表示するだけに留める(2026-07-15修正: 従来はpost_entry()のみスキップし、mark_used()/
save_history()は無条件実行されていたため、ドライラン実行のたびに本番の使用済み
トピック・価格履歴が意図せず書き換わってしまう問題があった。過去に手動でgit checkoutして
復旧させた実績あり(本ファイル過去の記録参照)。dry_run時は保存処理ごとスキップするよう修正)。
"""
from __future__ import annotations

import os
import sys
import traceback
from datetime import datetime, timedelta, timezone

# Windowsのローカルコンソール(既定cp932)では、価格表記の「¥」等一部の記号を含む
# 日本語print文でUnicodeEncodeErrorが発生することが確認されている(Demonで先行対応済み、
# 2026-07-15 SA全体点検のローカル動作確認でAngelでも同様の潜在リスクを確認)。標準出力/
# エラー出力をUTF-8に固定して回避する(GitHub Actions実行時(Linux, 既定UTF-8)には
# 影響しない安全な変更)。
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from blog_auto_post import price_history, topics
from blog_auto_post.article_pipeline import ArticlePipeline
from blog_auto_post.config import ConfigError, load_settings
from blog_auto_post.hatena_client import HatenaAPIError, post_entry
from blog_auto_post.rakuten_client import RakutenAPIError, fetch_products_for_topic
from blog_auto_post.scoring import compute_scores
from blog_auto_post.table_builder import (
    PRODUCT_TABLE_PLACEHOLDER,
    build_comparison_table_html,
    build_disclaimer_html,
)

JST = timezone(timedelta(hours=9))


def _already_posted_today(all_topics: list, now_jst: datetime) -> bool:
    """本日(JST)分の投稿が既にあるかどうかを判定する。

    2026-07-16、Dragon(app/main.py)でGitHub Actionsのスケジュール実行遅延を
    手動workflow_dispatchで補ったところ、後から遅延していたスケジュール実行も
    発火し、同日に記事が2本投稿される事故が発生した(Angel/Demonでも同日に同型の
    事故が実際に発生していたことを2026-07-17に確認)。再発防止のため、トピックの
    使用済み日時(JST換算)が本日と一致するものが1件でもあれば、それ以降の実行は
    投稿をスキップする。
    """
    today = now_jst.date()
    for t in all_topics:
        used_at = t.get("used_at")
        if not used_at:
            continue
        try:
            used_dt = datetime.fromisoformat(used_at)
        except ValueError:
            continue
        if used_dt.astimezone(JST).date() == today:
            return True
    return False


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
    except Exception as e:
        notify_failure("topic_selection", e)
        return 1

    now_jst = datetime.now(JST)
    if _already_posted_today(all_topics, now_jst):
        print(
            f"[main] 本日({now_jst:%Y-%m-%d} JST)は既に投稿済みのため、今回の実行はスキップします"
            "(スケジュール遅延と手動実行が重なった場合の二重投稿防止ガード)"
        )
        return 0

    print(f"[main] 選定トピック: {topic['title']} (id={topic['id']})")

    # 2. 楽天API商品データ取得 --------------------------------------------
    try:
        products = fetch_products_for_topic(
            search_queries=topic["search_queries"],
            app_id=settings.rakuten_app_id,
            access_key=settings.rakuten_access_key,
            origin_domain=settings.hatena_blog_domain,
            affiliate_id=settings.rakuten_affiliate_id,
        )
        if not products:
            raise RakutenAPIError("商品データが1件も取得できませんでした")
        print(f"[main] 楽天APIから商品 {len(products)} 件取得")
    except Exception as e:  # RakutenAPIError含む予期せぬ例外も安全に捕捉する
        notify_failure("rakuten_fetch", e)
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

    # 5. 比較表・免責文言の組み込み ------------------------------------------
    fetched_at_jst = datetime.now(JST).strftime("%Y-%m-%d %H:%M JST")
    table_html = build_comparison_table_html(products, trend_notes)
    disclaimer_html = build_disclaimer_html(fetched_at_jst)

    final_html = draft.body_html.replace(PRODUCT_TABLE_PLACEHOLDER, table_html)
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
        print("[main] === ANGEL_DRY_RUN=true: post_entry()・データ保存は実行していません(本番未反映) ===")
        print(f"[main] 投稿予定タイトル: {draft.title!r}")
        print(f"[main] 投稿予定本文冒頭(200文字): {final_html[:200]!r}")
        print(f"[main] 投稿予定URL(推定・実際の値は投稿後に確定): {dry_run_url}")
        print(f"[main] 投稿予定カテゴリ: {[topic['category'], '型落ちガジェット比較']}")
        return 0

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
