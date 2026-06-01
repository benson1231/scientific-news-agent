import os
import re
import sys
import time
import feedparser
import requests
from datetime import datetime, timezone, timedelta
from openai import OpenAI, RateLimitError

FEEDS = {
    "Nature": "https://www.nature.com/nature.rss",
    "Cell": "https://www.cell.com/cell/current.rss",
}

MAX_ARTICLES_PER_JOURNAL = 5

OPENROUTER_HEADERS = {
    "HTTP-Referer": "https://github.com/benson1231/scientific-news-agent",
    "X-OpenRouter-Title": "Scientific News Agent",
}

# openrouter/free 會自動從目前可用的免費模型中選擇，無需維護 model ID 清單
# 後面的 llama 作為備援（萬一 free router 也被限速）
OPENROUTER_MODELS = [
    "openrouter/free",
    "meta-llama/llama-3.2-3b-instruct:free",
]


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


def call_llm(client: OpenAI, prompt: str, max_tokens: int = 1200) -> str | None:
    """依序嘗試各個免費模型，rate limit 時切換下一個；全部失敗則等待後重試一次。"""
    min_wait = 35
    for model in OPENROUTER_MODELS:
        try:
            print(f"    >> 嘗試模型: {model}")
            response = client.chat.completions.create(
                extra_headers=OPENROUTER_HEADERS,
                model=model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=max_tokens,
            )
            print(f"    >> 成功使用: {model}")
            return response.choices[0].message.content.strip()
        except RateLimitError as e:
            wait = 35
            try:
                wait = int(e.body["error"]["metadata"]["retry_after_seconds"]) + 5
            except (KeyError, TypeError, AttributeError):
                pass
            min_wait = min(min_wait, wait)
            print(f"    >> Rate limit: {model}，切換下一個...")
        except Exception as e:
            print(f"    >> 失敗: {model} — {e}")

    print(f"    >> 所有模型都被限速，等待 {min_wait} 秒後重試...")
    time.sleep(min_wait)
    try:
        model = OPENROUTER_MODELS[0]
        print(f"    >> 重試: {model}")
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=max_tokens,
        )
        print(f"    >> 成功使用: {model}")
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"    >> 重試失敗: {e}")
        return None


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

    result = call_llm(client, prompt)
    if result:
        print(result)
        return result

    print("    >> LLM 全部失敗，僅輸出標題")
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
    print("  [OK] Slack 通知已送出")


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

    for journal, rss_url in FEEDS.items():
        print(f"\n{'='*50}")
        print(f"  {journal}")
        print(f"{'='*50}")

        print(f"\n[1/2] 抓取 RSS Feed...")
        all_articles[journal] = fetch_articles(rss_url)
        articles = all_articles[journal]
        print(f"  取得 {len(articles)} 篇文章：")
        for i, a in enumerate(articles, 1):
            pub = f"  ({a['published']})" if a['published'] else ""
            print(f"  [{i}] {a['title']}{pub}")

        print(f"\n[2/2] 呼叫 LLM 產生摘要（依序嘗試 {len(OPENROUTER_MODELS)} 個免費模型）...")
        all_summaries[journal] = summarize_articles(articles, journal, client)

    print(f"\n{'='*50}")
    print("  發送 Slack 通知")
    print(f"{'='*50}\n")
    payload = build_slack_payload(all_summaries, all_articles)
    send_to_slack(webhook_url, payload)
    print("\n完成！")


if __name__ == "__main__":
    main()
