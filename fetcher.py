import re
import feedparser
from config import MAX_ARTICLES_PER_JOURNAL, SKIP_PREFIXES


def strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text).strip()


def fetch_articles(
    rss_url: str,
    max_articles: int = MAX_ARTICLES_PER_JOURNAL,
    link_filter: str | None = None,
) -> list[dict]:
    feed = feedparser.parse(rss_url)
    articles = []
    for entry in feed.entries:
        title = strip_html(entry.get("title", ""))
        link = entry.get("link", "")
        if any(title.startswith(prefix) for prefix in SKIP_PREFIXES):
            continue
        if link_filter and link_filter not in link:
            continue
        raw_summary = strip_html(entry.get("summary", entry.get("description", "")))
        clean_summary = re.sub(
            r'^[\w\s]+,\s*Published online:[^;]+;\s*doi:\S+\s*', '', raw_summary
        ).strip()
        if not clean_summary or clean_summary == title:
            clean_summary = "(RSS 未提供摘要)"
        articles.append({
            "title": title,
            "summary": clean_summary[:800],
            "link": link,
            "published": entry.get("published", ""),
        })
        if len(articles) >= max_articles:
            break
    return articles
