import { PackageSearch } from 'lucide-react';
import SectionLayout from './SectionLayout';
import MonthlyTco2BarChart from '../components/MonthlyTco2BarChart';
import ActivitiesRankedList from '../components/ActivitiesRankedList';
import DataSourcesList from '../components/DataSourcesList';
import { useScope } from '../hooks/useScope';

export default function Scope3View() {
  const { scopeTotal, bySource, sparkline, documents, loading, error, retry } = useScope(3);

  return (
    <SectionLayout
      title="Scope 3 – Waste & Shipping"
      subtitle="Value chain emissions"
      icon={<PackageSearch size={20} color="white" />}
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
      {!error && !loading && scopeTotal === 0 && documents.length === 0 && (
        <p className="text-sm opacity-80 mb-4" style={{ color: 'var(--color-text)' }}>
          No Scope 3 data yet. Add documents with shipping or waste to see metrics here.
        </p>
      )}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div className="rounded-2xl p-5 border" style={{ background: 'var(--color-card)', boxShadow: 'var(--shadow-card)', borderColor: 'var(--color-card-outline)' }}>
          <p className="text-xs font-semibold uppercase tracking-widest opacity-70" style={{ color: 'var(--color-text)' }}>Scope 3 total</p>
          {loading ? (
            <div className="h-10 w-24 rounded-lg bg-slate-200 animate-pulse mt-2" />
          ) : (
            <p className="text-2xl font-bold mt-1" style={{ color: 'var(--color-text)' }}>
              {scopeTotal.toFixed(2)} <span className="text-base font-semibold opacity-70">tCO₂e</span>
            </p>
          )}
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 items-start">
        <MonthlyTco2BarChart data={sparkline} loading={loading} />
        <div style={{ minHeight: '320px' }}>
          <ActivitiesRankedList data={bySource} loading={loading} />
        </div>
      </div>

      <div style={{ minHeight: '200px' }}>
        <DataSourcesList
          documents={documents}
          loading={loading}
          title="Data sources for Scope 3"
          subtitle="Documents used for waste & shipping metrics"
        />
      </div>
    </SectionLayout>
  );
}
