# API

Interactive docs: `http://localhost:8000/docs` (OpenAPI). All routes are under `/api`.

| Area | Endpoints |
|---|---|
| System | `GET /health`, `GET /overview`, `GET /jobs/{id}`, `GET /settings`, `PUT /settings/llm` |
| Projects | `POST/GET /projects`, `GET/PATCH /projects/{id}`, `DELETE /projects/{id}?confirm_name=…`, `GET /projects/{id}/timeline` |
| Observations | `POST/GET /projects/{id}/observations` (multipart: file, acquisition_date, label), `GET /observations/{id}`, `/observations/{id}/preview` |
| AOIs | `POST /projects/{id}/aois`, `POST …/aois/upload` (GeoJSON), `GET …/aois`, `DELETE /aois/{id}`, `GET /aois/{id}/events` |
| Analyses | `POST /projects/{id}/analyses`, `POST /analyses/{id}/start`, `GET /analyses/{id}`, `/status`, `/summary`, `/preflight`, `/image/{before|after|mask|overlay}`, `/compare/{other}`, `/geojson` |
| Events | `GET /projects/{id}/events` (filters: analysis_id, confidence_min/max, review_status, cluster, priority_min, temporal_status, bbox, sort, limit), `GET /events/{uid}`, `/events/{uid}/crop/{kind}` |
| Clusters | `GET /projects/{id}/clusters`, `GET /clusters/{uid}` |
| Review | `POST /events/{uid}/review`, `POST /projects/{id}/events/bulk-review` (confirm=true), `GET /projects/{id}/review-history` |
| Reports | `POST /projects/{id}/reports`, `GET /projects/{id}/reports`, `GET /reports/{id}`, `/reports/{id}/pdf`, `GET /analyses/{id}/export/csv|geojson` |
| Satellite | `GET /satellite/status`, `POST /satellite/search`, `GET /satellite/scenes/{id}/quicklook`, `POST /satellite/projects/{id}/import` |
| Model | `GET /model/status|metrics|dataset|architecture|training`, `POST /model/training` (confirm), `POST /model/evaluate` |
| Assistant | `GET /assistant/providers`, `POST/GET /assistant/conversations`, `GET/DELETE /assistant/conversations/{id}`, `POST …/messages` (`stream=true` ⇒ SSE), `GET /assistant/offline-summary/{analysis}` |

Event ids: the public `event_id` is `EVT-###` (unique within an analysis); `uid` = `<analysis_id>:EVT-###` is globally unique and used in URLs.
Long-running work (analysis, training, evaluation, satellite import) returns a `job_id`; poll `GET /jobs/{id}` or the analysis status.
