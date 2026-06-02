import os
import sys
from openai import OpenAI

from config import FEEDS
from fetcher import fetch_articles
from summarizer import summarize_articles
from notifier import build_slack_payload, send_to_slack


def main() -> None:
    api_key = os.environ.get("OPENROUTER_API_KEY")
    webhook_url = os.environ.get("SLACK_WEBHOOK_URL")

    if not api_key or not webhook_url:
        print("Error: OPENROUTER_API_KEY and SLACK_WEBHOOK_URL environment variables are required.")
        sys.exit(1)

    client = OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=api_key,
    )

    all_articles: dict[str, list] = {}
    all_summaries: dict[str, str] = {}

    for journal, feed_cfg in FEEDS.items():
        print(f"\n{'='*50}")
        print(f"  {journal}")
        print(f"{'='*50}")

        print(f"\n[1/2] 抓取 RSS Feed...")
        all_articles[journal] = fetch_articles(
            feed_cfg["url"], link_filter=feed_cfg["link_filter"]
        )
        articles = all_articles[journal]
        print(f"  取得 {len(articles)} 篇文章：")
        for i, a in enumerate(articles, 1):
            pub = f"  ({a['published']})" if a['published'] else ""
            print(f"  [{i}] {a['title']}{pub}")

        print(f"\n[2/2] 呼叫 LLM 產生摘要...")
        all_summaries[journal] = summarize_articles(articles, journal, client)

    print(f"\n{'='*50}")
    print("  發送 Slack 通知")
    print(f"{'='*50}\n")
    payload = build_slack_payload(all_summaries, all_articles)
    send_to_slack(webhook_url, payload)
    print("\n完成！")


if __name__ == "__main__":
    main()
