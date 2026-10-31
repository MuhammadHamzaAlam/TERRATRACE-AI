import L from "leaflet";
import { useEffect, useMemo } from "react";
import { ImageOverlay, MapContainer, Polygon, Tooltip, useMap } from "react-leaflet";
import { api } from "../../services/api";
import type { Analysis, EventRec } from "../../types/api";
import { STATUS_COLOR } from "../../lib/format";

export type ViewMode = "before" | "after" | "overlay" | "mask" | "swipe";

function Fit({ bounds }: { bounds: L.LatLngBoundsExpression }) {
  const map = useMap();
  useEffect(() => { const lb = L.latLngBounds(bounds as L.LatLngTuple[]); map.fitBounds(lb); map.setMaxBounds(lb.pad(0.5)); }, [map, bounds]);
  return null;
}
function Swipe({ pos, url, bounds }: { pos: number; url: string; bounds: L.LatLngBoundsExpression }) {
  const map = useMap();
  useEffect(() => {
    const layer = L.imageOverlay(url, bounds, { zIndex: 5 }).addTo(map);
    const clip = () => {
      const el = layer.getElement(); if (!el) return;
      const size = map.getSize(); el.style.clipPath = `inset(0 0 0 ${pos * 100}%)`; void size;
    };
    clip(); layer.on("load", clip); map.on("move zoom", clip);
    return () => { map.off("move zoom", clip); layer.remove(); };
  }, [map, url, bounds, pos]);
  return null;
}

/** Before/after viewer in image coordinates (L.CRS.Simple). Events are drawn from stored pixel bounding boxes. */
export default function AnalysisViewer({ analysis, mode, opacity, events, selectedUid, highlight, onSelect, swipe = 0.5 }: {
  analysis: Analysis; mode: ViewMode; opacity: number; events: EventRec[]; selectedUid: string | null; highlight: string[]; onSelect: (uid: string) => void; swipe?: number;
}) {
  const [w, h] = analysis.image_size;
  const bounds = useMemo<L.LatLngBoundsExpression>(() => [[0, 0], [h, w]], [w, h]);
  const toLL = (x: number, y: number): L.LatLngTuple => [h - y, x];
  return (
    <MapContainer key={analysis.id} crs={L.CRS.Simple} bounds={bounds} minZoom={-3} maxZoom={4} zoomSnap={0.25} className="h-full w-full" attributionControl={false}>
      <Fit bounds={bounds} />
      {(mode === "before" || mode === "overlay" || mode === "swipe") && <ImageOverlay url={api.analyses.imageUrl(analysis.id, "before")} bounds={bounds} />}
      {mode === "after" && <ImageOverlay url={api.analyses.imageUrl(analysis.id, "after")} bounds={bounds} />}
      {mode === "overlay" && analysis.has_mask && <ImageOverlay url={api.analyses.imageUrl(analysis.id, "overlay")} bounds={bounds} opacity={opacity} />}
      {mode === "mask" && analysis.has_mask && <ImageOverlay url={api.analyses.imageUrl(analysis.id, "mask")} bounds={bounds} />}
      {mode === "swipe" && <Swipe pos={swipe} url={api.analyses.imageUrl(analysis.id, "after")} bounds={bounds} />}
      {events.map((e) => {
        const [x0, y0, x1, y1] = e.bbox_px; const sel = e.uid === selectedUid; const hl = highlight.includes(e.event_id);
        return (
          <Polygon key={e.uid} positions={[toLL(x0, y0), toLL(x1, y0), toLL(x1, y1), toLL(x0, y1)]} eventHandlers={{ click: () => onSelect(e.uid) }}
            pathOptions={{ color: sel ? "#ffffff" : hl ? "#ffd166" : STATUS_COLOR[e.review_status], weight: sel || hl ? 3 : 1.5, fill: false }}>
            <Tooltip>{e.event_id} · conf {e.confidence.toFixed(2)} · priority {e.priority_score.toFixed(0)}</Tooltip>
          </Polygon>
        );
      })}
    </MapContainer>
  );
}
