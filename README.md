# Scientific News Agent

每天早上自動抓取 **Nature** 與 **Cell** 最新論文，透過 OpenRouter 免費 LLM 產生繁體中文摘要，並發送至 Slack。

## 運作流程

```
GitHub Actions (每天 09:00 台灣時間)
  → 抓取 Nature / Cell RSS Feed
  → 呼叫 OpenRouter API (LLaMA 3.1 免費模型) 生成繁體中文摘要
  → 傳送 Slack Webhook 通知
```

## 設定步驟

### 1. 取得 OpenRouter API Key

前往 [openrouter.ai](https://openrouter.ai) 註冊並取得 API Key。  
使用 `meta-llama/llama-3.1-8b-instruct:free` 模型，**完全免費**。

### 2. 建立 Slack Incoming Webhook

1. 前往 Slack App 管理頁面建立新 App
2. 啟用 **Incoming Webhooks**
3. 新增一個 Webhook 並複製 URL（格式：`https://hooks.slack.com/services/...`）

### 3. 設定 GitHub Secrets

在 GitHub 倉庫 → **Settings → Secrets and variables → Actions** 新增：

| Secret 名稱 | 說明 |
|---|---|
| `OPENROUTER_API_KEY` | OpenRouter API Key |
| `SLACK_WEBHOOK_URL` | Slack Webhook URL |

### 4. 啟用 GitHub Actions

將程式碼推送至 GitHub 後，Actions 會：
- **每天 09:00（台灣時間）自動執行**
- 可在 GitHub UI 的 Actions 頁面手動觸發測試

## 本機測試

```bash
pip install -r requirements.txt

export OPENROUTER_API_KEY="your_key_here"
export SLACK_WEBHOOK_URL="https://hooks.slack.com/services/..."

python agent.py
```

## 自訂設定

在 [agent.py](agent.py) 頂部修改以下參數：

```python
FEEDS = {
    "Nature": "https://www.nature.com/nature.rss",
    "Cell":   "https://www.cell.com/cell/current.rss",
    # 可新增其他期刊 RSS
}

MAX_ARTICLES_PER_JOURNAL = 5   # 每個期刊最多抓幾篇
OPENROUTER_MODEL = "meta-llama/llama-3.1-8b-instruct:free"  # 可替換其他免費模型
```

### 可替換的免費 OpenRouter 模型

| 模型 ID | 說明 |
|---|---|
| `meta-llama/llama-3.1-8b-instruct:free` | 速度快，適合摘要（預設） |
| `mistralai/mistral-7b-instruct:free` | 品質穩定 |
| `google/gemma-2-9b-it:free` | Google 開源模型 |

## 通知範例

Slack 訊息格式：

```
📰 科學論文日報 — 2026年06月01日

🔬 Nature（5 篇）
[1] 標題中文翻譯
    摘要說明...

🧬 Cell（5 篇）
...
```
