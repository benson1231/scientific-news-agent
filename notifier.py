import requests
from datetime import datetime, timezone, timedelta


def build_slack_payload(summaries: dict[str, str], articles: dict[str, list]) -> dict:
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
