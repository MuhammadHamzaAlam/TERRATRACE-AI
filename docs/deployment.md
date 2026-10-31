# Deployment

## Local (recommended)

```bash
cp .env.example .env
docker compose up --build        # UI http://localhost:8080  API http://localhost:8000/docs
```
Mount your trained checkpoint at `./models/siamese_unet/best.pt` (and optionally LEVIR-CD at `./data/raw/LEVIR-CD`). Ollama runs on the host (see [ollama-setup.md](ollama-setup.md)).
GPU: install the NVIDIA Container Toolkit, replace the CPU torch wheel in `backend/Dockerfile` with the default PyPI wheels and add `deploy.resources.reservations.devices` to the backend service.

## Cloud (not performed in this build)

| Component | Suggestion | Notes |
|---|---|---|
| Frontend | Vercel/Netlify static build (`npm run build`, env `VITE_API_BASE=https://<backend>/api`) | needs backend CORS: `CORS_ORIGINS=https://<frontend>` |
| Backend | Render/Railway/Fly Docker service (`backend/Dockerfile`) | ≥ 2 GB RAM (PyTorch); persistent disk for `/data`; use PostgreSQL (`DATABASE_URL`) for multi-instance; one worker (jobs are in-process) |
| Model artifact | GitHub Release asset or object storage; download into `/models/siamese_unet/best.pt` at start | checkpoint ≈ 60 MB (not committed) |
| LLM | (1) local full stack with Ollama; (2) cloud backend + `XAI_API_KEY`; (3) cloud backend → secured private Ollama over VPN/authenticated proxy | a laptop's Ollama is not reachable from a cloud host; never expose Ollama unauthenticated |

No cloud deployment was attempted or verified in this build (no hosting accounts/authorisation were provided); no live URLs exist.
