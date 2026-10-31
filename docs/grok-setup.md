# Grok (xAI) setup — optional, paid API

```bash
echo 'XAI_API_KEY=xai-...'      >> .env      # server-side only; never sent to the browser, never logged
echo 'XAI_MODEL=<model id from https://docs.x.ai/>' >> .env   # choose a tool-capable model
echo 'LLM_PROVIDER=grok'        >> .env      # or switch in Settings
```

TerraTrace calls `POST {XAI_BASE_URL}/chat/completions` (default `https://api.x.ai/v1`) with streaming and the same tool definitions as Ollama.
401 → "invalid key", 404 → "model not found", 429/5xx → up to 2 retries honouring `retry-after`, then a clear rate-limit message. Usage (token counts) is logged without credentials.
Using this provider sends the *tool results needed for the answer* (event ids, counts, areas) to xAI; nothing is sent unless a user asks the assistant a question or enables report narrative.

Status: implemented and tested against mocked HTTP transports only — **no live xAI call was made** (no API key was provided).
