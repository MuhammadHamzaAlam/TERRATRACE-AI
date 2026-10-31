# Security

Implemented: content-sniffed uploads with extension allowlist, size limit (streamed, partial files deleted), server-generated filenames, storage confined to `data/storage`, Pydantic validation everywhere,
SQLAlchemy ORM only (no string SQL), CORS allowlist, per-IP rate limit, `nosniff`, request error isolation, job timeouts via provider timeouts, secrets only via environment variables (never returned by any endpoint; verified by test),
guarded project deletion, bulk review confirmation, LLM tool allowlist + argument validation + project scoping + read-only default + UI-action allowlist (backend and frontend), prompt-injection hygiene, Ollama base URL not runtime-settable.

**Not implemented / limitations — do not treat as production-hardened or certified**
* **No user authentication.** Reviewer identity is a self-declared header; project scoping exists in the tool layer but there are no per-user access controls on REST endpoints. Run on a trusted network or put an authenticating proxy in front.
* In-memory rate limiter (per process). No CSRF concerns without cookies, but also no auth tokens.
* Uploaded rasters are parsed by GDAL/OpenCV — keep dependencies patched; no antivirus scanning.
* LLM output is not a security boundary: tools are. A malicious model could still call any read-only tool in the active project.
* SQLite file in `data/`; back it up. Training/evaluation endpoints can consume large CPU/RAM.
