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


SKIP_PREFIXES = (
    "Author Correction:",
    "Publisher Correction:",
    "Correction:",
    "Erratum:",
    "Retraction:",
)


def fetch_articles(rss_url: str) -> list[dict]:
    feed = feedparser.parse(rss_url)
    articles = []
    for entry in feed.entries:
        title = strip_html(entry.get("title", ""))
        if any(title.startswith(prefix) for prefix in SKIP_PREFIXES):
            continue
        articles.append({
            "title": title,
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


def summarize_articles(
    articles: list[dict], journal: str, client: OpenAI
) -> tuple[str, list[dict]]:
    """回傳 (摘要文字, LLM 選出的文章清單)，文章清單用於附上連結。"""
    if not articles:
        return f"今日 {journal} 暫無新文章。", []

    n_select = min(MAX_ARTICLES_PER_JOURNAL, len(articles))
    articles_text = "\n\n".join(
        f"[{i+1}] 標題: {a['title']}\n摘要: {a['summary']}"
        for i, a in enumerate(articles)
    )

    prompt = (
        f"以下是 {journal} 期刊共 {len(articles)} 篇最新論文（含序號）：\n\n"
        f"{articles_text}\n\n"
        f"請從中挑選最具科學影響力的 {n_select} 篇，依重要性由高到低排序，"
        f"用繁體中文為每篇提供 2-3 句摘要，說明其科學意義。\n"
        f"回覆格式：每篇以原始序號開頭，例如：\n"
        f"[3] 標題中文翻譯\n摘要內容...\n\n"
        f"只回覆選出的 {n_select} 篇，不需要其他說明。"
    )

    result = call_llm(client, prompt, max_tokens=1500)
    if not result:
        print("    >> LLM 全部失敗，僅輸出標題")
        return "\n".join(f"• {a['title']}" for a in articles[:n_select]), []

    print(result)

    # 從 LLM 輸出解析 [n] 序號，取得對應文章（用於連結）
    selected: list[dict] = []
    seen: set[int] = set()
    for m in re.finditer(r'\[(\d+)\]', result):
        idx = int(m.group(1)) - 1  # 轉 0-indexed
        if 0 <= idx < len(articles) and idx not in seen:
            selected.append(articles[idx])
            seen.add(idx)

    return result, selected


def build_slack_payload(
    summaries: dict[str, str],
    total_counts: dict[str, int],
    selected: dict[str, list[dict]],
) -> dict:
    today = datetime.now(timezone(timedelta(hours=8))).strftime("%Y年%m月%d日")
    journal_emoji = {"Nature": "🔬", "Cell": "🧬"}

    blocks: list[dict] = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": f"📰 科學論文日報 — {today}"},
        },
    ]

    for journal, summary in summaries.items():
        emoji = journal_emoji.get(journal, "📄")
        total = total_counts.get(journal, 0)
        picked = selected.get(journal, [])

        blocks.append({"type": "divider"})
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f"*{emoji} {journal}*"
                    f"（從 {total} 篇中選出最重要 {len(picked)} 篇）\n\n"
                    f"{summary}"
                ),
            },
        })

        if picked:
            links = "\n".join(f"• <{a['link']}|{a['title']}>" for a in picked)
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

    all_summaries: dict[str, str] = {}
    all_total_counts: dict[str, int] = {}
    all_selected: dict[str, list[dict]] = {}

    for journal, rss_url in FEEDS.items():
        print(f"\n{'='*50}")
        print(f"  {journal}")
        print(f"{'='*50}")

        print(f"\n[1/2] 抓取 RSS Feed...")
        articles = fetch_articles(rss_url)
        all_total_counts[journal] = len(articles)
        print(f"  取得 {len(articles)} 篇文章：")
        for i, a in enumerate(articles, 1):
            pub = f"  ({a['published']})" if a['published'] else ""
            print(f"  [{i}] {a['title']}{pub}")

        print(f"\n[2/2] 呼叫 LLM 排序並摘要（從 {len(articles)} 篇選出最重要 {MAX_ARTICLES_PER_JOURNAL} 篇）...")
        summary, selected = summarize_articles(articles, journal, client)
        all_summaries[journal] = summary
        all_selected[journal] = selected
        print(f"\n  選出 {len(selected)} 篇連結已解析")

    print(f"\n{'='*50}")
    print("  發送 Slack 通知")
    print(f"{'='*50}\n")
    payload = build_slack_payload(all_summaries, all_total_counts, all_selected)
    send_to_slack(webhook_url, payload)
    print("\n完成！")


if __name__ == "__main__":
    main()
