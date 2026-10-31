# Sentinel-2 / Copernicus Data Space

* **Search** (`POST /api/satellite/search`) uses the public OData catalogue — no credentials. Filters: bbox, dates, L2A product type, cloud cover. Verified live.
* **Download/import** (`POST /api/satellite/projects/{id}/import`) needs a free CDSE account: `CDSE_USERNAME`, `CDSE_PASSWORD` (password-grant token, client `cdse-public`). Without them the endpoint returns 409 and the UI explains why.
* To avoid ~1 GB zips only the 10 m true-colour band (`TCI_10m`) and 20 m scene classification (`SCL_20m`) are fetched through the OData *Nodes* API, cropped to the AOI, and written as an RGB GeoTIFF in the scene's UTM CRS.
* **Cloud masking**: SCL classes 0,1,3,8,9,10,11 (no-data, saturated, shadow, cloud medium/high, cirrus, snow) are resampled (nearest) onto the 10 m grid and zeroed as nodata; masked fraction is recorded.
* **Domain gap (important)**: the model is trained on 0.5 m imagery; Sentinel-2 is 10 m (×20 coarser). Observations from Sentinel-2 are flagged `unvalidated`; an analysis on them is **blocked** unless the user explicitly sets `allow_domain_gap`, and results are labelled exploratory. No performance claim is made for Sentinel-2.
* No automatic band-stretch/domain-adaptation is applied beyond TCI's own 8-bit scaling.

Status: search — tested live. Download/crop/mask — implemented and unit-tested only on synthetic rasters; **not exercised against a real download** (no credentials in the build environment).
