# Multi-date monitoring

A *project* holds many dated *observations*. An *analysis* compares two of them (any pair, consecutive pairs, first-vs-latest, or the
first/last observation inside a date range — see **New analysis**). Each analysis is stored independently with its events, clusters,
masks, model version and configuration.

## Temporal event association (`app/monitoring/association.py`)

Different event IDs in different analyses do **not** imply different physical structures. After every completed analysis the
project's tracks are rebuilt deterministically:

1. Completed analyses are processed in order of the *after* observation date.
2. For each analysis, every event is compared with every existing track (the track's latest polygon):
   * **match** if polygon IoU ≥ 0.1 **or** centroid distance ≤ max(12 m [16 px when not georeferenced], equivalent radius of the larger polygon);
   * geographic matching uses a local metric projection when both sides are georeferenced; pixel matching is attempted only between
     analyses with identical pixel grids.
3. Greedy one-to-one assignment (best IoU, then nearest) — a track receives at most one event per analysis.
4. Unmatched events start new tracks (`temporal_status = new`); matched events join the track (`recurring`).
5. A track stores first/last observed date and observation count; each event stores `track_id`, so confidences and review states over time
   are queryable (`GET /api/events/{id}` → `track.observations`).
6. Priority scores are recomputed afterwards so the recurrence factor reflects the history.

## Interpreting the outputs

* **New**: location not detected in any earlier analysis. **Recurring**: detected in ≥ 2 analyses (for cumulative comparisons such as
  first-vs-March and first-vs-June this means a *persistent* change; for consecutive comparisons it means repeated change at one place).
* **No longer detected**: tracks present in analysis A but absent in B (`GET /api/analyses/{A}/compare/{B}` → `not_detected_in_b`).
* Dashboards show only stored analyses; missing periods are **not** interpolated, and every view states that detections ≠ confirmed
  real-world change.

## Limits

Greedy matching can merge adjacent structures or split one that changed shape; thresholds are fixed constants (not user-tunable yet);
tracks do not model splits/merges.
