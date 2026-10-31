# Human verification

Statuses: `pending` → `confirmed` | `rejected` | `needs_investigation` (any transition between statuses is allowed; a no-op requires a note).

* `POST /api/events/{uid}/review {status, notes}` — reviewer identity from the `X-Reviewer` header (editable in the UI header). Local build has no
  authentication, so identity is self-declared; see [security.md](security.md).
* Every change appends an immutable `EventHistory` row (previous status, new status, reviewer, notes, timestamp).
* `POST /api/projects/{id}/events/bulk-review` requires `confirm=true` (the UI shows a confirmation dialog), ≤ 500 ids, and refuses ids outside the project.
* Review Center: filters (status, high/low confidence, priority, cluster), event inspector with before/after crops, predicted mask, confidence,
  priority breakdown, location, track history; audit-history tab.
* **The LLM has no write path.** The tool registry contains no review tool (enforced by a test that allows only `get_/list_/query_/compare_/generate_` names);
  the assistant can only filter the view or say events need review.
