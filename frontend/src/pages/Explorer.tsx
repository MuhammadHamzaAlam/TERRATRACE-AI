import L from "leaflet";
import { useEffect, useMemo, useState } from "react";
import { GeoJSON, LayersControl, MapContainer, ImageOverlay, TileLayer, useMap } from "react-leaflet";
import { Link } from "react-router-dom";
import EventInspector from "../features/review/EventInspector";
import { Empty, ErrorBox, Notice, PageHeader, Spinner } from "../components/ui";
import { useApp } from "../hooks/AppState";
import { useAsync } from "../hooks/useAsync";
import { STATUS_COLOR } from "../lib/format";
import { api } from "../services/api";
import { REVIEW_LABELS, type ReviewStatus } from "../types/api";

function FitTo({ bounds }: { bounds: L.LatLngBoundsExpression | null }) {
  const map = useMap();
  useEffect(() => { if (bounds) map.fitBounds(bounds, { padding: [30, 30] }); }, [map, bounds]);
  return null;
}

export default function Explorer() {
  const app = useApp(); const a = app.analysis;
  const [conf, setConf] = useState(0); const [status, setStatus] = useState(""); const [cluster, setCluster] = useState(""); const [temporal, setTemporal] = useState("");
  const geo = useAsync(() => (a && a.georeferenced && a.status === "completed" ? api.analyses.geojson(a.id) : Promise.resolve(null)), [a?.id, a?.status]);
  const ev = useAsync(() => (a && app.projectId && a.georeferenced && a.status === "completed" ? api.events.list(app.projectId, { analysis_id: a.id, limit: 1000 }) : Promise.resolve(null)), [a?.id, a?.status]);
  const cls = useAsync(() => (a && app.projectId && a.georeferenced ? api.events.clusters(app.projectId, a.id) : Promise.resolve([])), [a?.id]);
  const aois = useAsync(() => (app.projectId ? api.projects.aois(app.projectId) : Promise.resolve([])), [app.projectId]);
  const obs = useAsync(() => (a ? api.projects.observations(a.project_id) : Promise.resolve([])), [a?.id]);

  const visible = useMemo(() => {
    const keep = new Set((ev.data?.events ?? []).filter((e) =>
      e.confidence >= Math.max(conf, app.filter.confidence_min ?? 0) && (!(status || app.filter.review_status) || e.review_status === (status || app.filter.review_status)) &&
      (!(cluster || app.selectedCluster) || e.cluster === (cluster || app.selectedCluster)) && (!temporal || e.temporal_status === temporal) && (!app.filter.ids || app.filter.ids.includes(e.event_id))).map((e) => e.event_id));
    return { type: "FeatureCollection", features: (geo.data?.features ?? []).filter((f) => keep.has(String(f.id))) } as GeoJSON.FeatureCollection;
  }, [ev.data, geo.data, conf, status, cluster, temporal, app.filter, app.selectedCluster]);
  const bounds = useMemo<L.LatLngBoundsExpression | null>(() => {
    const b = obs.data?.find((o) => o.id === a?.before_observation_id)?.bounds_wgs84; return b ? [[b[1], b[0]], [b[3], b[2]]] : null;
  }, [obs.data, a?.before_observation_id]);
  const beforeObs = obs.data?.find((o) => o.id === a?.before_observation_id);

  if (!a) return <div><PageHeader title="Geospatial explorer" /><Empty title="No analysis selected"><Link to="/new-analysis" className="btn-primary">New analysis</Link></Empty></div>;
  if (!a.georeferenced) return <div><PageHeader title="Geospatial explorer" /><div className="p-6"><Notice tone="warn"><b>{a.id} is not georeferenced.</b> Its detections have image-relative coordinates only, so no map markers are shown (TerraTrace never invents locations). Use the <Link to="/workspace" className="underline">Workspace</Link> viewer, or upload GeoTIFF / import Sentinel-2 imagery for a map view.</Notice></div></div>;
  return (
    <div className="flex h-full flex-col">
      <PageHeader title="Geospatial explorer" subtitle={`${a.id} · ${visible.features.length} of ${ev.data?.total ?? 0} candidate events shown`} />
      <div className="grid min-h-0 flex-1 lg:grid-cols-[minmax(0,1fr)_360px]">
        <div className="relative min-h-[460px]">
          <div className="absolute left-14 top-3 z-[500] flex flex-wrap items-center gap-3 rounded-md border border-ink-700 bg-ink-900/95 p-2 text-xs">
            <label className="flex items-center gap-1">Min conf {conf.toFixed(2)}<input type="range" min={0} max={1} step={0.05} value={conf} onChange={(e) => setConf(+e.target.value)} aria-label="Minimum confidence" /></label>
            <select className="input !w-40 !py-1" value={status} onChange={(e) => setStatus(e.target.value)} aria-label="Review status filter"><option value="">All statuses</option>{(Object.keys(REVIEW_LABELS) as ReviewStatus[]).map((s) => <option key={s} value={s}>{REVIEW_LABELS[s]}</option>)}</select>
            <select className="input !w-28 !py-1" value={cluster} onChange={(e) => setCluster(e.target.value)} aria-label="Cluster filter"><option value="">All clusters</option>{(cls.data ?? []).map((c) => <option key={c.uid} value={c.cluster_id}>{c.cluster_id}</option>)}</select>
            <select className="input !w-28 !py-1" value={temporal} onChange={(e) => setTemporal(e.target.value)} aria-label="Temporal filter"><option value="">new + recurring</option><option value="new">new</option><option value="recurring">recurring</option></select>
            {(app.filter.ids || app.selectedCluster) && <button className="btn-ghost !py-0.5" onClick={() => { app.setFilter({}); app.selectCluster(null); }}>Clear assistant filter</button>}
          </div>
          <MapContainer center={[0, 0]} zoom={2} className="h-full w-full" maxZoom={21}>
            <FitTo bounds={bounds} />
            <LayersControl position="topright">
              <LayersControl.BaseLayer checked name="Esri World Imagery"><TileLayer attribution="Tiles © Esri — Maxar, Earthstar Geographics" url="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}" maxNativeZoom={19} maxZoom={21} /></LayersControl.BaseLayer>
              <LayersControl.BaseLayer name="OpenStreetMap"><TileLayer attribution="© OpenStreetMap contributors" url="https://tile.openstreetmap.org/{z}/{x}/{y}.png" maxNativeZoom={19} maxZoom={21} /></LayersControl.BaseLayer>
              {beforeObs?.bounds_wgs84 && bounds && <LayersControl.Overlay name="Before image (bounds approx.)"><ImageOverlay url={api.analyses.imageUrl(a.id, "before")} bounds={bounds} opacity={0.9} /></LayersControl.Overlay>}
              {beforeObs?.bounds_wgs84 && bounds && <LayersControl.Overlay name="After image (bounds approx.)"><ImageOverlay url={api.analyses.imageUrl(a.id, "after")} bounds={bounds} opacity={0.9} /></LayersControl.Overlay>}
              <LayersControl.Overlay checked name="AOIs">{<GeoJSON key={"aoi" + (aois.data?.length ?? 0)} data={{ type: "FeatureCollection", features: (aois.data ?? []).map((x) => ({ type: "Feature", properties: { name: x.name }, geometry: x.geometry })) } as GeoJSON.FeatureCollection} style={{ color: "#e0a458", weight: 2, dashArray: "6 4", fill: false }} />}</LayersControl.Overlay>
              <LayersControl.Overlay checked name="Clusters">{<GeoJSON key={"cl" + (cls.data?.length ?? 0) + (app.selectedCluster ?? "")} data={{ type: "FeatureCollection", features: (cls.data ?? []).filter((c) => c.boundary_geo).map((c) => ({ type: "Feature", properties: { id: c.cluster_id, n: c.event_count }, geometry: c.boundary_geo! })) } as GeoJSON.FeatureCollection}
                style={(f) => ({ color: f?.properties?.id === app.selectedCluster ? "#fff" : "#8ab4f8", weight: f?.properties?.id === app.selectedCluster ? 3 : 1.5, fillOpacity: 0.06 })} onEachFeature={(f, l) => l.bindTooltip(`${f.properties.id}: ${f.properties.n} events`)} />}</LayersControl.Overlay>
              <LayersControl.Overlay checked name="Candidate events"><GeoJSON key={visible.features.map((f) => f.id).join() + app.highlightIds.join() + (app.selectedEventUid ?? "")} data={visible}
                style={(f) => { const p = f!.properties as { review_status: ReviewStatus; event_id: string }; const hl = app.highlightIds.includes(p.event_id); return { color: hl ? "#ffd166" : STATUS_COLOR[p.review_status], weight: hl ? 4 : 2, fillOpacity: 0.3 }; }}
                onEachFeature={(f, l) => { l.bindTooltip(`${f.properties.event_id} · conf ${f.properties.confidence} · P${f.properties.priority_score}`); l.on("click", () => app.selectEvent(`${a.id}:${f.properties.event_id}`)); }} /></LayersControl.Overlay>
            </LayersControl>
          </MapContainer>
        </div>
        <aside className="min-h-0 overflow-auto border-l border-ink-700 bg-ink-850">
          {app.selectedEventUid && app.selectedEventUid.startsWith(a.id) ? <div><button className="btn-ghost m-3" onClick={() => app.selectEvent(null)}>← Close</button><EventInspector uid={app.selectedEventUid} onChanged={() => { ev.reload(); geo.reload(); }} /></div> :
            <div className="space-y-3 p-4 text-sm"><h3 className="label">Legend</h3>{(Object.keys(REVIEW_LABELS) as ReviewStatus[]).map((s) => <div key={s} className="flex items-center gap-2 text-xs"><span className="h-2.5 w-2.5 rounded-sm" style={{ background: STATUS_COLOR[s] }} />{REVIEW_LABELS[s]}</div>)}
              <Notice>Polygons are model-predicted candidate changes georeferenced from the raster's CRS. Image overlays use WGS84 bounding boxes and are approximate for rotated/projected rasters. Click a polygon to inspect it.</Notice>
              {ev.loading && <Spinner />}{ev.error && <ErrorBox message={ev.error} />}</div>}
        </aside>
      </div>
    </div>
  );
}
