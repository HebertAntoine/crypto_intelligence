import { NavLink, Navigate, Route, Routes } from "react-router-dom";
import { useEffect, useState } from "react";
import Today from "./pages/Today";
import Dashboard from "./pages/Dashboard";
import AssetPage from "./pages/AssetPage";
import GlobalMarketPage from "./pages/GlobalMarket";
import SourcesPage from "./pages/Sources";
import CalendarPage from "./pages/Calendar";
import ResearchPage from "./pages/Research";
import KnowledgePage from "./pages/Knowledge";
import DailyReportPage from "./pages/DailyReport";
import MarketStructurePage from "./pages/MarketStructure";
import TrackRecordPage from "./pages/TrackRecord";
import ChartsPatternsPage from "./pages/ChartsPatterns";
import TraderKnowledgePage from "./pages/TraderKnowledge";
import { api, type Health } from "./lib/api";

export default function App() {
  const [health, setHealth] = useState<Health | null>(null);

  useEffect(() => {
    api.health().then(setHealth).catch(() => setHealth(null));
  }, []);

  return (
    <div className="app">
      <header className="header">
        <h1>Crypto Intelligence</h1>
        {health && (
          <span className={health.mock_mode ? "badge-mode" : "badge-live"}>
            {health.mock_mode ? "MOCK MODE" : "LIVE DATA"}
          </span>
        )}
        {health && !health.llm.enabled && (
          <span className="pill pill-info" title={health.llm.reason ?? ""}>
            NO LLM — deterministic analysis
          </span>
        )}
        <nav>
          <NavLink to="/" end>Today</NavLink>
          <NavLink to="/daily">Daily Report</NavLink>
          <NavLink to="/global">Global</NavLink>
          <NavLink to="/calendar">Calendar</NavLink>
          <NavLink to="/chart">Graphiques &amp; Patterns</NavLink>
          <NavLink to="/trader-knowledge">Trader Knowledge</NavLink>
          <NavLink to="/structure">Structure</NavLink>
          <NavLink to="/track-record">Track Record</NavLink>
          <NavLink to="/research">Research</NavLink>
          <NavLink to="/knowledge">Knowledge</NavLink>
          <NavLink to="/sources">Sources</NavLink>
        </nav>
      </header>

      <main className="main">
        <Routes>
          <Route path="/" element={<Today />} />
          <Route path="/dashboard" element={<Dashboard />} />
          <Route path="/daily" element={<DailyReportPage />} />
          <Route path="/structure" element={<MarketStructurePage />} />
          <Route path="/chart" element={<ChartsPatternsPage />} />
          <Route path="/trader-knowledge" element={<TraderKnowledgePage />} />
          <Route path="/track-record" element={<TrackRecordPage />} />
          <Route path="/asset/:symbol" element={<AssetPage />} />
          <Route path="/global" element={<GlobalMarketPage />} />
          <Route path="/calendar" element={<CalendarPage />} />
          <Route path="/research" element={<ResearchPage />} />
          <Route path="/knowledge" element={<KnowledgePage />} />
          <Route path="/sources" element={<SourcesPage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>

        <div className="disclaimer">
          Analysis tool only. It places no orders and gives no investment advice.
          Every decision is yours.
        </div>
      </main>
    </div>
  );
}
