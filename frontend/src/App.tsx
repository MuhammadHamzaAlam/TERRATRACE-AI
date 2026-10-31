import { Route, Routes } from "react-router-dom";
import Layout from "./components/Layout";
import Overview from "./pages/Overview";
import Projects from "./pages/Projects";
import NewAnalysis from "./pages/NewAnalysis";
import Workspace from "./pages/Workspace";
import Explorer from "./pages/Explorer";
import Temporal from "./pages/Temporal";
import ReviewCenter from "./pages/ReviewCenter";
import Analytics from "./pages/Analytics";
import Assistant from "./pages/Assistant";
import Reports from "./pages/Reports";
import ModelLab from "./pages/ModelLab";
import Settings from "./pages/Settings";

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<Overview />} />
        <Route path="projects" element={<Projects />} />
        <Route path="new-analysis" element={<NewAnalysis />} />
        <Route path="workspace" element={<Workspace />} />
        <Route path="explorer" element={<Explorer />} />
        <Route path="temporal" element={<Temporal />} />
        <Route path="review" element={<ReviewCenter />} />
        <Route path="analytics" element={<Analytics />} />
        <Route path="assistant" element={<Assistant />} />
        <Route path="reports" element={<Reports />} />
        <Route path="model" element={<ModelLab />} />
        <Route path="settings" element={<Settings />} />
        <Route path="*" element={<div className="p-8 text-slate2-400">Page not found.</div>} />
      </Route>
    </Routes>
  );
}
