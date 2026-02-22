import { Droplets } from 'lucide-react';
import SectionLayout from './SectionLayout';
import DataSourcesList from '../components/DataSourcesList';
import MonthlyTco2BarChart from '../components/MonthlyTco2BarChart';
import { useWater } from '../hooks/useWater';

export default function WaterView() {
  const { water_usage, sparkline, documents, loading, error, retry } = useWater();

  return (
    <SectionLayout
      title="Water Usage"
      subtitle="Non-GHG water consumption and data sources"
      icon={<Droplets size={20} color="white" />}
    >
      {error && (
        <div className="flex items-center gap-3 p-4 rounded-xl border mb-4" style={{ background: 'rgba(254,226,226,0.5)', borderColor: 'var(--color-card-outline)' }}>
          <p className="text-sm text-rose-700 flex-1" title={error}>{error}</p>
          <button
            type="button"
            onClick={() => retry()}
            className="text-sm font-semibold px-4 py-2 rounded-lg text-white shrink-0"
            style={{ background: 'var(--chart-primary)' }}
          >
            Retry
          </button>
        </div>
      )}
      {!error && !loading && water_usage.volume_m3 === 0 && documents.length === 0 && (
        <p className="text-sm opacity-80 mb-4" style={{ color: 'var(--color-text)' }}>
          No water data yet. Add documents with water usage to see metrics here.
        </p>
      )}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        <div className="rounded-2xl p-5 border" style={{ background: 'var(--color-card)', boxShadow: 'var(--shadow-card)', borderColor: 'var(--color-card-outline)' }}>
          <p className="text-xs font-semibold uppercase tracking-widest opacity-70" style={{ color: 'var(--color-text)' }}>Volume (m³)</p>
          {loading ? (
            <div className="h-10 w-20 rounded-lg bg-slate-200 animate-pulse mt-2" />
          ) : (
            <p className="text-2xl font-bold mt-1" style={{ color: 'var(--color-text)' }}>
              {water_usage.volume_m3.toFixed(1)} <span className="text-base font-semibold opacity-70">m³</span>
            </p>
          )}
        </div>
        <div className="rounded-2xl p-5 border" style={{ background: 'var(--color-card)', boxShadow: 'var(--shadow-card)', borderColor: 'var(--color-card-outline)' }}>
          <p className="text-xs font-semibold uppercase tracking-widest opacity-70" style={{ color: 'var(--color-text)' }}>Volume (gallons)</p>
          {loading ? (
            <div className="h-10 w-24 rounded-lg bg-slate-200 animate-pulse mt-2" />
          ) : (
            <p className="text-2xl font-bold mt-1" style={{ color: 'var(--color-text)' }}>
              {water_usage.volume_gallons.toLocaleString(undefined, { maximumFractionDigits: 0 })} <span className="text-base font-semibold opacity-70">gal</span>
            </p>
          )}
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 items-stretch">
        <MonthlyTco2BarChart data={sparkline} loading={loading} />
        <DataSourcesList documents={documents} loading={loading} />
      </div>
    </SectionLayout>
  );
}
