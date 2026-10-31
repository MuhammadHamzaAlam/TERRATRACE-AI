# Deployment

## Local (recommended)

```bash
cp .env.example .env
docker compose up --build        # UI http://localhost:8080  API http://localhost:8000/docs
```
Mount your trained checkpoint at `./models/siamese_unet/best.pt` (and optionally LEVIR-CD at `./data/raw/LEVIR-CD`). Ollama runs on the host (see [ollama-setup.md](ollama-setup.md)).
GPU: install the NVIDIA Container Toolkit, replace the CPU torch wheel in `backend/Dockerfile` with the default PyPI wheels and add `deploy.resources.reservations.devices` to the backend service.

## Frontend on Vercel (config ready; **not deployed**)

`frontend/vercel.json` sets the Vite build and an SPA fallback rewrite. The UI is useless without a reachable backend, so deploy the backend first.

```bash
npm i -g vercel && cd frontend && vercel login
vercel link                                   # Root Directory: frontend
vercel env add VITE_API_BASE production       # e.g. https://<backend-host>/api  (baked in at build time)
vercel --prod
```
Then set `CORS_ORIGINS=https://<your-app>.vercel.app` on the backend. The assistant streams over SSE directly from the browser to the backend, so the backend host must not buffer responses.
Alternative: connect the GitHub repo in the Vercel dashboard with Root Directory `frontend` and the same env var.

## Cloud (not performed in this build)

| Component | Suggestion | Notes |
|---|---|---|
| Frontend | Vercel/Netlify static build (`npm run build`, env `VITE_API_BASE=https://<backend>/api`) | needs backend CORS: `CORS_ORIGINS=https://<frontend>` |
| Backend | Render/Railway/Fly Docker service (`backend/Dockerfile`) | ≥ 2 GB RAM (PyTorch); persistent disk for `/data`; use PostgreSQL (`DATABASE_URL`) for multi-instance; one worker (jobs are in-process) |
| Model artifact | GitHub Release asset or object storage; download into `/models/siamese_unet/best.pt` at start | checkpoint ≈ 60 MB (not committed) |
| LLM | (1) local full stack with Ollama; (2) cloud backend + `XAI_API_KEY`; (3) cloud backend → secured private Ollama over VPN/authenticated proxy | a laptop's Ollama is not reachable from a cloud host; never expose Ollama unauthenticated |

No cloud deployment was attempted or verified in this build (no hosting accounts/authorisation were provided); no live URLs exist.
