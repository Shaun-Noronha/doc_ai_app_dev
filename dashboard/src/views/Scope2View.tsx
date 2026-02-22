import { Zap } from 'lucide-react';
import SectionLayout from './SectionLayout';
import MonthlyTco2BarChart from '../components/MonthlyTco2BarChart';
import ActivitiesRankedList from '../components/ActivitiesRankedList';
import { useDashboard } from '../hooks/useDashboard';

export default function Scope2View() {
  const { kpis, bySource, loading } = useDashboard();
  const scope2Sources = bySource.filter((s) => s.scope === 2);

  return (
    <SectionLayout
      title="Scope 2 – Electricity"
      subtitle="Indirect emissions from purchased electricity"
      icon={<Zap size={20} color="white" />}
    >
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div className="rounded-2xl p-5 border" style={{ background: 'var(--color-card)', boxShadow: 'var(--shadow-card)', borderColor: 'var(--color-card-outline)' }}>
          <p className="text-xs font-semibold uppercase tracking-widest opacity-70" style={{ color: 'var(--color-text)' }}>Scope 2 total</p>
          {loading ? (
            <div className="h-10 w-24 rounded-lg bg-slate-200 animate-pulse mt-2" />
          ) : (
            <p className="text-2xl font-bold mt-1" style={{ color: 'var(--color-text)' }}>
              {(scope2Sources.reduce((sum, s) => sum + s.tco2e, 0)).toFixed(2)} <span className="text-base font-semibold opacity-70">tCO₂e</span>
            </p>
          )}
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 items-start">
        <MonthlyTco2BarChart data={kpis?.sparkline ?? []} loading={loading} />
        <div style={{ minHeight: '320px' }}>
          <ActivitiesRankedList data={scope2Sources} loading={loading} />
        </div>
      </div>
    </SectionLayout>
  );
}
