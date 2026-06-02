FEEDS = {
    "Nature": {"url": "https://www.nature.com/nature.rss", "link_filter": "s41586"},
    "Cell":   {"url": "https://www.cell.com/cell/current.rss", "link_filter": None},
}

MAX_ARTICLES_PER_JOURNAL = 5

OPENROUTER_HEADERS = {
    "HTTP-Referer": "https://github.com/benson1231/scientific-news-agent",
    "X-OpenRouter-Title": "Scientific News Agent",
}

OPENROUTER_MODEL = "openrouter/free"

SKIP_PREFIXES = (
    "Author Correction:",
    "Publisher Correction:",
    "Correction:",
    "Erratum:",
    "Retraction:",
)
