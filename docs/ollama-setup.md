# Ollama setup (default, local, free)

```bash
# 1. install: https://ollama.com/download   (Linux: curl -fsSL https://ollama.com/install.sh | sh)
ollama serve                      # starts on http://localhost:11434
# 2. pull a model that supports TOOL CALLING (not every model does)
ollama pull qwen3:8b              # good quality/size balance (≈ 5 GB, 8–16 GB RAM or a GPU)
ollama pull qwen3:1.7b            # tiny, CPU-friendly; adequate for simple lookups, weaker on multi-step questions
# 3. tell TerraTrace which model to use
echo 'OLLAMA_MODEL=qwen3:8b' >> .env      # or pick it in Settings / the Assistant sidebar
```

* Run the backend on the host: `OLLAMA_BASE_URL=http://localhost:11434` (default).
* Backend in Docker, Ollama on the host: `OLLAMA_BASE_URL=http://host.docker.internal:11434` (set by `docker-compose.yml`; on Linux the compose file adds `host-gateway`).
  Ollama must listen on an address reachable from the container (`OLLAMA_HOST=0.0.0.0:11434` on the host, firewall-restricted to the Docker bridge).
* **Never expose Ollama publicly** — it has no authentication. For a remote Ollama use a private network/VPN or an authenticating reverse proxy.
* The base URL is deliberately only settable by environment variable (SSRF protection), not from the UI.
* Errors surfaced to the user: server unreachable, model not installed (`ollama pull …` hint), model without tool support, timeout (CPU too slow), no model configured.

Tested model: see README → "LLM tool-calling test results" for the exact model and what was verified live versus mocked.
