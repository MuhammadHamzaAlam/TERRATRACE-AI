import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import Overview from "../pages/Overview";
import ObservationTimeline from "../features/monitoring/ObservationTimeline";
import ModelLab from "../pages/ModelLab";

const json = (b: unknown, status = 200) => Promise.resolve(new Response(JSON.stringify(b), { status, headers: { "Content-Type": "application/json" } }));
afterEach(() => vi.restoreAllMocks());

const overview = {
  counts: { projects: 2, analyses_completed: 3, analyses_total: 4, events: 17, events_pending: 12, events_confirmed: 2, monitoring_regions: 1, reports: 1 },
  model: { status: "trained", architecture: "Siamese U-Net", checkpoint_present: true, validated: false, inference_available: true, message: "Checkpoint present but not evaluated on the LEVIR-CD test split; metrics pending.", metrics: null },
  recent_reports: [], recent_activity: [], system: { database: "ok", satellite: { search_available: true, download_available: false, message: "x" }, llm: { provider: "ollama", ollama: { base_url: "http://localhost:11434", model: null }, grok: { api_key_configured: false, model: null } } },
};

describe("Overview", () => {
  it("renders live counts from the API and an honest model-pending notice", async () => {
    vi.stubGlobal("fetch", vi.fn(() => json(overview)));
    render(<MemoryRouter><Overview /></MemoryRouter>);
    expect(screen.getByRole("status")).toBeInTheDocument();                     // loading state
    await waitFor(() => expect(screen.getByText("17")).toBeInTheDocument());
    expect(screen.getByText(/metrics pending/)).toBeInTheDocument();
    expect(screen.getByText("12 pending · 2 confirmed")).toBeInTheDocument();
  });
  it("shows an error state with retry when the backend is unreachable", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.reject(new TypeError("fail"))));
    render(<MemoryRouter><Overview /></MemoryRouter>);
    expect(await screen.findByRole("alert")).toHaveTextContent(/Cannot reach the TerraTrace backend/);
    expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
  });
});

describe("ObservationTimeline", () => {
  it("renders only stored observations (no interpolated points)", () => {
    render(<ObservationTimeline tl={{ observations: [{ id: "O1", label: "a", date: "2025-01-10", source: "upload", georeferenced: false }, { id: "O2", label: "b", date: "2025-06-10", source: "upload", georeferenced: false }], analyses: [{ analysis_id: "A-1", before_date: "2025-01-10", after_date: "2025-06-10", n_events: 4, n_clusters: 1, changed_pct: 1, changed_area_m2: null }], tracks: { total: 0, recurring: 0, single: 0 }, note: "n" }} />);
    expect(screen.getByText("2025-01-10")).toBeInTheDocument(); expect(screen.getByText("2025-06-10")).toBeInTheDocument();
    expect(screen.getAllByRole("img", { name: "Observation timeline" })).toHaveLength(1);
  });
  it("shows an empty state with no observations", () => {
    render(<ObservationTimeline tl={{ observations: [], analyses: [], tracks: { total: 0, recurring: 0, single: 0 }, note: "" }} />);
    expect(screen.getByText("No observations yet.")).toBeInTheDocument();
  });
});

describe("ModelLab", () => {
  it("displays 'evaluation pending' instead of invented metrics when no checkpoint exists", async () => {
    vi.stubGlobal("fetch", vi.fn((url: string) => {
      if (url.endsWith("/model/status")) return json({ status: "not_initialized", architecture: "x", checkpoint_present: false, validated: false, inference_available: false, message: "Model evaluation pending — no validated checkpoint available.", metrics: null });
      if (url.endsWith("/model/metrics")) return json({ test_metrics: null, training_history: [], prediction_visualizations: [], message: "Model evaluation pending — no validated checkpoint available." });
      if (url.endsWith("/model/dataset")) return json({ available: false, root: "/x", splits: {}, source: "s", usage_note: "u" });
      if (url.endsWith("/model/architecture")) return json({ name: "Siamese U-Net", parameters: 15386897 });
      return json([]);
    }));
    render(<MemoryRouter><ModelLab /></MemoryRouter>);
    await waitFor(() => expect(screen.getAllByText(/Model evaluation pending/).length).toBeGreaterThan(0));
    expect(screen.queryByText(/F1/)).toBeNull();
    expect(screen.getByRole("button", { name: /Run evaluation/ })).toBeDisabled();
  });
});
