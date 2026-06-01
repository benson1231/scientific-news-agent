import os
import re
import sys
import feedparser
import requests
from datetime import datetime, timezone, timedelta
from openai import OpenAI

FEEDS = {
    "Nature": "https://www.nature.com/nature.rss",
    "Cell": "https://www.cell.com/cell/current.rss",
}

MAX_ARTICLES_PER_JOURNAL = 5
OPENROUTER_MODEL = "meta-llama/llama-3.2-3b-instruct:free"


def strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text).strip()


def fetch_articles(rss_url: str, max_articles: int = MAX_ARTICLES_PER_JOURNAL) -> list[dict]:
    feed = feedparser.parse(rss_url)
    articles = []
    for entry in feed.entries[:max_articles]:
        articles.append({
            "title": strip_html(entry.get("title", "")),
            "summary": strip_html(entry.get("summary", entry.get("description", "")))[:600],
            "link": entry.get("link", ""),
            "published": entry.get("published", ""),
        })
    return articles


def summarize_articles(articles: list[dict], journal: str, client: OpenAI) -> str:
    if not articles:
        return f"今日 {journal} 暫無新文章。"

    articles_text = "\n\n".join(
        f"[{i+1}] 標題: {a['title']}\n摘要: {a['summary']}"
        for i, a in enumerate(articles)
    )

    prompt = (
        f"以下是 {journal} 期刊的最新論文，請用繁體中文為每篇提供 2-3 句摘要，"
        f"並說明其科學意義或潛在影響。\n\n"
        f"{articles_text}\n\n"
        f"請以條列格式回覆，每篇以「[數字]」開頭，包含論文標題（繁體中文翻譯）與摘要。"
    )

    try:
        response = client.chat.completions.create(
            model=OPENROUTER_MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=1200,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"Warning: LLM summarization failed for {journal}: {e}")
        return "\n".join(f"• {a['title']}" for a in articles)


def build_slack_payload(summaries: dict[str, str], articles: dict[str, list]) -> dict:
    today = datetime.now(timezone(timedelta(hours=8))).strftime("%Y年%m月%d日")

    journal_emoji = {"Nature": "🔬", "Cell": "🧬"}

    blocks = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": f"📰 科學論文日報 — {today}"},
        },
    ]

    for journal, summary in summaries.items():
        emoji = journal_emoji.get(journal, "📄")
        article_list = articles.get(journal, [])

        blocks.append({"type": "divider"})
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*{emoji} {journal}*（共 {len(article_list)} 篇）\n{summary}",
            },
        })

        if article_list:
            links = "\n".join(
                f"• <{a['link']}|{a['title']}>"
                for a in article_list[:3]
            )
            blocks.append({
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"*原文連結:*\n{links}"},
            })

    blocks.append({"type": "divider"})
    blocks.append({
        "type": "context",
        "elements": [{"type": "mrkdwn", "text": "由 scientific-news-agent 自動產生 · OpenRouter LLM 摘要"}],
    })

    return {"blocks": blocks}


def send_to_slack(webhook_url: str, payload: dict) -> None:
    response = requests.post(webhook_url, json=payload, timeout=15)
    response.raise_for_status()
    print("Slack notification sent successfully.")


def main() -> None:
    api_key = os.environ.get("OPENROUTER_API_KEY")
    webhook_url = os.environ.get("SLACK_WEBHOOK_URL")

    if not api_key or not webhook_url:
        print("Error: OPENROUTER_API_KEY and SLACK_WEBHOOK_URL environment variables are required.")
        sys.exit(1)

    client = OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=api_key,
        default_headers={
            "HTTP-Referer": "https://github.com/benson1231/scientific-news-agent",
            "X-Title": "Scientific News Agent",
        },
    )

    all_articles: dict[str, list] = {}
    all_summaries: dict[str, str] = {}

    for journal, rss_url in FEEDS.items():
        print(f"Fetching {journal} RSS...")
        all_articles[journal] = fetch_articles(rss_url)
        print(f"  Found {len(all_articles[journal])} articles.")

        print(f"Summarizing {journal} with LLM...")
        all_summaries[journal] = summarize_articles(all_articles[journal], journal, client)

    payload = build_slack_payload(all_summaries, all_articles)
    print("Sending to Slack...")
    send_to_slack(webhook_url, payload)


if __name__ == "__main__":
    main()
