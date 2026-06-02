from openai import OpenAI
from config import OPENROUTER_MODEL, OPENROUTER_HEADERS


def call_llm(client: OpenAI, prompt: str, max_tokens: int = 1200) -> str | None:
    try:
        print(f"    >> 呼叫模型: {OPENROUTER_MODEL}")
        response = client.chat.completions.create(
            extra_headers=OPENROUTER_HEADERS,
            model=OPENROUTER_MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=max_tokens,
        )
        content = response.choices[0].message.content
        if not content:
            raise ValueError("empty response content")
        print(f"    >> 成功")
        return content.strip()
    except Exception as e:
        print(f"    >> 失敗: {e}")
        return None
