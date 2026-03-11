import { useState } from 'react';
import { Activity, Zap, Droplets, Recycle, TrendingDown, Bell, Settings, FilePlus } from 'lucide-react';
import KpiCard from '../components/KpiCard';
import ScopeDonut from '../components/ScopeDonut';
import MonthlyTco2BarChart from '../components/MonthlyTco2BarChart';
import RecommendationCard from '../components/RecommendationCard';
import UploadModal from '../components/UploadModal';
import { useDashboard } from '../hooks/useDashboard';

function SkeletonCard() {
  return (
    <div className="rounded-2xl p-5 flex flex-col gap-3 min-h-[160px]"
      style={{ background: 'var(--color-card)', boxShadow: 'var(--shadow-card)' }}>
      <div className="h-3 w-24 rounded bg-slate-200 animate-pulse" />
      <div className="h-9 w-32 rounded bg-slate-200 animate-pulse mt-2" />
      <div className="h-3 w-40 rounded bg-slate-100 animate-pulse mt-1" />
    </div>
  );
}

export default function Dashboard() {
  const { kpis, byScope, bySource, recommendations, loading, error, retry } = useDashboard();
  const [showUpload, setShowUpload] = useState(false);

  const today = new Date().toLocaleDateString('en-US', {
    weekday: 'long', year: 'numeric', month: 'long', day: 'numeric',
  });

  return (
    <div className="min-h-screen flex flex-col" style={{ background: 'var(--color-bg)' }}>
      {/* Top header bar */}
      <header className="sticky top-0 z-40 flex items-center justify-between px-8 py-4"
        style={{
          background: 'rgba(254,250,224,0.9)',
          backdropFilter: 'blur(16px)',
          borderBottom: '1px solid var(--color-card-outline)',
        }}
      >
        <div>
          <h1 className="text-xl font-bold" style={{ color: 'var(--color-text)' }}>Sip Happens</h1>
          <p className="text-xs mt-0.5 opacity-70" style={{ color: 'var(--color-text)' }}>{today}</p>
        </div>
        <div className="flex items-center gap-3">
          {error && (
            <div className="flex items-center gap-2">
              <span className="text-xs bg-rose-100 text-rose-600 border border-rose-200 px-3 py-1.5 rounded-full font-medium max-w-xs truncate" title={error}>
                {error}
              </span>
              <button
                type="button"
                onClick={() => retry()}
                className="text-xs font-semibold px-3 py-1.5 rounded-full text-white transition-colors"
                style={{ background: 'var(--chart-primary)' }}
              >
                Refresh dashboard
              </button>
            </div>
          )}
          {/* Add Document */}
          <button
            onClick={() => setShowUpload(true)}
            className="flex items-center gap-2 px-4 py-2 text-sm font-semibold text-white rounded-xl transition-all hover:opacity-90 active:scale-95"
            style={{ background: 'linear-gradient(135deg, #059669 0%, #10b981 100%)', boxShadow: '0 2px 8px rgba(5,150,105,0.35)' }}
          >
            <FilePlus size={15} />
            Add Document
          </button>
          <button className="w-9 h-9 rounded-xl flex items-center justify-center text-slate-500 hover:text-slate-700 hover:bg-white transition-all"
            style={{ boxShadow: 'var(--shadow-card)' }}>
            <Bell size={17} />
          </button>
          <button className="w-9 h-9 rounded-xl flex items-center justify-center hover:bg-white/80 transition-all"
            style={{ color: 'var(--color-text)', boxShadow: 'var(--shadow-card)' }}>
            <Settings size={17} />
          </button>
          <div className="w-9 h-9 rounded-xl flex items-center justify-center text-white text-sm font-bold shrink-0"
            style={{ background: 'var(--chart-primary)' }}>
            S
          </div>
        </div>
      </header>

      {/* Main content */}
      <main className="flex-1 px-8 py-6 flex flex-col gap-6 max-w-[1600px] w-full mx-auto">

        {/* ── KPI row (skeletons on load) ──────────────────── */}
        <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-4">
          {loading && !kpis ? (
            [...Array(4)].map((_, i) => <SkeletonCard key={i} />)
          ) : (
            <>
          {/* Total Emissions */}
          <KpiCard
            title="Total Emissions"
            value={kpis ? kpis.total_emissions_tco2e : 0}
            unit="tCO₂e"
            subtext="All scopes combined"
            icon={<Activity size={18} color="white" />}
            iconBg="#054A29"
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
            iconBg="#054A29"
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
            iconBg="#054A29"
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
            iconBg="#054A29"
            progressRing={kpis ? kpis.waste_diversion_rate : 0}
            loading={loading}
          />
            </>
          )}
        </div>

        {/* ── Charts row: Scope donut + Monthly analysis (date filter) ───── */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 items-stretch">
          <div style={{ minHeight: '420px' }}>
            <ScopeDonut data={byScope} loading={loading} />
          </div>
          <div style={{ minHeight: '420px' }}>
            <MonthlyTco2BarChart data={kpis?.sparkline ?? []} loading={loading} />
          </div>
        </div>

        {/* ── AI Recommendations ──────────────────────────── */}
        <section>
          {/* Section header */}
          <div className="flex items-center gap-3 mb-4">
            <div className="w-8 h-8 rounded-xl flex items-center justify-center" style={{ background: 'var(--chart-primary)' }}>
              <TrendingDown size={16} color="white" />
            </div>
            <div>
              <h2 className="text-sm font-bold uppercase tracking-widest" style={{ color: 'var(--color-text)' }}>Recommended Actions</h2>
              <p className="text-xs opacity-70" style={{ color: 'var(--color-text)' }}>Realistic ways to grow your sustainability</p>
            </div>
          </div>

          {loading ? (
            <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
              {[...Array(2)].map((_, i) => (
                <div key={i} className="rounded-2xl p-5 h-40 animate-pulse"
                  style={{ background: 'var(--color-card)', boxShadow: 'var(--shadow-card)' }} />
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
        <footer className="pt-2 pb-4 text-center text-xs opacity-70" style={{ color: 'var(--color-text)' }}>
          SME Sustainability Pulse · Data sourced from Document AI pipeline · Emission factors: EPA 2023
        </footer>
      </main>

      {/* Upload modal – rendered outside main flow so it overlays everything */}
      {showUpload && (
        <UploadModal
          onClose={() => setShowUpload(false)}
          onDone={() => { setShowUpload(false); retry(); }}
        />
      )}
    </div>
  );
}
