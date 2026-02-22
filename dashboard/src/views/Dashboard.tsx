import { Activity, Zap, Droplets, Recycle, TrendingDown, Bell, Settings } from 'lucide-react';
import KpiCard from '../components/KpiCard';
import ScopeDonut from '../components/ScopeDonut';
import SourceBarChart from '../components/SourceBarChart';
import RecommendationCard from '../components/RecommendationCard';
import { useDashboard } from '../hooks/useDashboard';

export default function Dashboard() {
  const { kpis, byScope, bySource, recommendations, loading, error } = useDashboard();

  const today = new Date().toLocaleDateString('en-US', {
    weekday: 'long', year: 'numeric', month: 'long', day: 'numeric',
  });

  return (
    <div className="min-h-screen flex flex-col" style={{ background: 'var(--color-bg)' }}>
      {/* Top header bar */}
      <header className="sticky top-0 z-40 flex items-center justify-between px-8 py-4"
        style={{
          background: 'rgba(241,245,249,0.85)',
          backdropFilter: 'blur(16px)',
          borderBottom: '1px solid rgba(15,23,42,0.06)',
        }}
      >
        <div>
          <h1 className="text-xl font-bold text-slate-800">Sustainability Dashboard</h1>
          <p className="text-xs text-slate-400 mt-0.5">{today}</p>
        </div>
        <div className="flex items-center gap-3">
          {error && (
            <span className="text-xs bg-rose-100 text-rose-600 border border-rose-200 px-3 py-1.5 rounded-full font-medium">
              {error}
            </span>
          )}
          <button className="w-9 h-9 rounded-xl flex items-center justify-center text-slate-500 hover:text-slate-700 hover:bg-white transition-all"
            style={{ boxShadow: 'var(--shadow-card)' }}>
            <Bell size={17} />
          </button>
          <button className="w-9 h-9 rounded-xl flex items-center justify-center text-slate-500 hover:text-slate-700 hover:bg-white transition-all"
            style={{ boxShadow: 'var(--shadow-card)' }}>
            <Settings size={17} />
          </button>
          <div className="w-9 h-9 rounded-xl bg-emerald-500 flex items-center justify-center text-white text-sm font-bold shrink-0">
            S
          </div>
        </div>
      </header>

      {/* Main content */}
      <main className="flex-1 px-8 py-6 flex flex-col gap-6 max-w-[1600px] w-full mx-auto">

        {/* ── KPI row ─────────────────────────────────────── */}
        <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-4">
          {/* Total Emissions */}
          <KpiCard
            title="Total Emissions"
            value={kpis ? kpis.total_emissions_tco2e : 0}
            unit="tCO₂e"
            subtext="All scopes combined"
            icon={<Activity size={18} color="white" />}
            iconBg="linear-gradient(135deg, #059669 0%, #10b981 100%)"
            sparkline={kpis?.sparkline ?? []}
            loading={loading}
            trend={kpis ? (kpis.total_emissions_tco2e > 0 ? 'neutral' : 'down') : 'neutral'}
            trendText="vs. baseline period"
          />

          {/* Energy Intensity */}
          <KpiCard
            title="Energy Intensity"
            value={kpis ? kpis.energy_kwh.toLocaleString(undefined, { maximumFractionDigits: 0 }) : 0}
            unit="kWh"
            subtext="Total electricity consumed"
            icon={<Zap size={18} color="white" />}
            iconBg="linear-gradient(135deg, #0ea5e9 0%, #38bdf8 100%)"
            loading={loading}
            trend="neutral"
            trendText="Scope 2 consumption"
          />

          {/* Water */}
          <KpiCard
            title="Water Consumption"
            value={kpis ? kpis.water_m3.toLocaleString(undefined, { maximumFractionDigits: 1 }) : 0}
            unit="m³"
            subtext="Total water usage"
            icon={<Droplets size={18} color="white" />}
            iconBg="linear-gradient(135deg, #0891b2 0%, #22d3ee 100%)"
            loading={loading}
            trend="neutral"
            trendText="Non-GHG metric"
          />

          {/* Waste Diversion */}
          <KpiCard
            title="Waste Diversion Rate"
            value={kpis ? Math.round(kpis.waste_diversion_rate) : 0}
            unit="%"
            subtext="Recycled + composted"
            icon={<Recycle size={18} color="white" />}
            iconBg="linear-gradient(135deg, #7c3aed 0%, #a78bfa 100%)"
            progressRing={kpis ? kpis.waste_diversion_rate : 0}
            loading={loading}
          />
        </div>

        {/* ── Charts row ──────────────────────────────────── */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 items-stretch">
          <div style={{ minHeight: '420px' }}>
            <ScopeDonut data={byScope} loading={loading} />
          </div>
          <div style={{ minHeight: '420px' }}>
            <SourceBarChart data={bySource} loading={loading} />
          </div>
        </div>

        {/* ── AI Recommendations ──────────────────────────── */}
        <section>
          {/* Section header */}
          <div className="flex items-center gap-3 mb-4">
            <div className="w-8 h-8 rounded-xl flex items-center justify-center"
              style={{ background: 'linear-gradient(135deg, #059669 0%, #10b981 100%)' }}>
              <TrendingDown size={16} color="white" />
            </div>
            <div>
              <h2 className="text-sm font-bold uppercase tracking-widest text-slate-600">AI Recommendations</h2>
              <p className="text-xs text-slate-400">Actionable improvements based on your sustainability data</p>
            </div>
          </div>

          {loading ? (
            <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
              {[...Array(2)].map((_, i) => (
                <div key={i} className="rounded-2xl p-5 h-40 bg-white/70 animate-pulse"
                  style={{ boxShadow: 'var(--shadow-card)' }} />
              ))}
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
              {recommendations.map((rec) => (
                <RecommendationCard key={rec.id} rec={rec} />
              ))}
            </div>
          )}
        </section>

        {/* ── Footer ──────────────────────────────────────── */}
        <footer className="pt-2 pb-4 text-center text-xs text-slate-400">
          SME Sustainability Pulse · Data sourced from Document AI pipeline · Emission factors: EPA 2023
        </footer>
      </main>
    </div>
  );
}
