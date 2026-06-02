from openai import OpenAI
from llm import call_llm


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

    result = call_llm(client, prompt, max_tokens=2000)
    if result:
        print(result)
        return result

    print("    >> LLM 全部失敗，僅輸出標題")
    return "\n".join(f"• {a['title']}" for a in articles)
