# Geospatial processing

## Ingestion (`app/geospatial/raster.py`)

* Accepts GeoTIFF, PNG, JPEG. The file **content** is sniffed (not just the extension); corrupt files, <64 px images and
  rasters with <3 bands are rejected.
* GeoTIFF with CRS + non-identity transform ⇒ *georeferenced*: CRS string, 6-term affine, WGS84 bounds and ground sample
  distance are stored on the observation. Otherwise the observation is *image-relative*: pixel coordinates and pixel areas only —
  no map markers, no GeoJSON, no directional queries.
* 16-bit/float rasters are percentile-stretched (2–98 %) to 8-bit RGB; nodata is zeroed.

## Alignment

`check_alignment` compares a pair: footprint overlap (<50 % ⇒ unsuitable, <90 % ⇒ warning), CRS/transform/size mismatches
(⇒ the *after* raster is re-projected onto the *before* grid with Rasterio bilinear resampling), and georeferenced-vs-not
mismatch (unsuitable). Unreferenced images of different sizes are **blocked, not resized**. After loading, a phase-correlation
estimate of the global shift is stored; shifts > 8 px add a warning.

## Domain compatibility

LEVIR-CD GSD is 0.5 m. `domain_compatibility(gsd)`: ≤ 1 m `compatible`; ≤ 3 m `warning`; coarser `unvalidated` (analysis is blocked
unless the user sets `allow_domain_gap`, and all outputs carry the flag). Unknown GSD ⇒ `unknown`.

## Events (`app/geospatial/events.py`)

Probability ≥ threshold → morphological opening → 8-connected components → drop components < `min_event_pixels` →
bounding box, centroid, area, mean/max/min probability, contour polygon (Douglas–Peucker). With georeferencing, polygon vertices
are transformed pixel → CRS (affine) → WGS84 (PyProj, `always_xy`), and `area_m2 = pixel_count × geodesic area of one pixel` on the
WGS84 ellipsoid, so areas are correct in any CRS. Components are named **candidate change events**.

## Clustering (`clustering.py`)

DBSCAN on event centroids. Georeferenced: coordinates are projected to a local azimuthal-equidistant plane (metres), `eps` in metres
(default 50). Otherwise `eps` in pixels (default 64). Each cluster stores count, total area, centroid, extent, mean confidence, convex-hull
boundary (GeoJSON) and mean event priority. Parameters are per-analysis and user-adjustable.

## Priority (`priority.py`)

`score = 100 · Σ wᵢ·fᵢ` with factors area (log-scaled vs. largest event), confidence, cluster concentration, relative change (share of
image, saturating at 2 %) and temporal recurrence. Default weights 0.30/0.30/0.20/0.10/0.10, configurable per analysis. Every event stores
factors, weights and per-factor contributions; the UI plots them. It is an **analytical priority**, never a threat score; the LLM may
explain it but cannot change it.
