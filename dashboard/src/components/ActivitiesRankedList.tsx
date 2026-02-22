import type { SourceEmission } from '../types';

interface Props {
  data: SourceEmission[];
  loading?: boolean;
}

export default function ActivitiesRankedList({ data, loading }: Props) {
  const sorted = [...data].sort((a, b) => b.tco2e - a.tco2e);
  const maxTco2e = sorted.length ? Math.max(...sorted.map((d) => d.tco2e)) : 0;

  return (
    <div
      className="rounded-2xl p-6 flex flex-col gap-4 h-full"
      style={{
        background: 'var(--color-card)',
        backdropFilter: 'blur(16px)',
        WebkitBackdropFilter: 'blur(16px)',
        boxShadow: 'var(--shadow-card)',
      }}
    >
      <div>
        <h3 className="text-sm font-semibold uppercase tracking-widest" style={{ color: 'var(--color-text)' }}>
          Activities by CO₂ emissions
        </h3>
        <p className="text-xs mt-0.5 opacity-80" style={{ color: 'var(--color-text)' }}>
          Ranked by highest emissions (tCO₂e)
        </p>
      </div>

      {loading ? (
        <div className="flex-1 flex flex-col gap-3 justify-center">
          {[...Array(5)].map((_, i) => (
            <div key={i} className="flex items-center gap-3">
              <div className="w-6 h-6 rounded bg-slate-200 animate-pulse shrink-0" />
              <div className="flex-1 h-4 bg-slate-200 rounded animate-pulse" style={{ width: `${70 - i * 10}%` }} />
              <div className="w-14 h-4 bg-slate-100 rounded animate-pulse" />
            </div>
          ))}
        </div>
      ) : (
        <ul className="flex-1 flex flex-col gap-3 min-h-0">
          {sorted.map((item, index) => {
            const pct = maxTco2e > 0 ? (item.tco2e / maxTco2e) * 100 : 0;
            return (
              <li
                key={`${item.source}-${item.scope}-${index}`}
                className="flex items-center gap-3"
                style={{ color: 'var(--color-text)' }}
              >
                <span
                  className="w-7 h-7 rounded-lg flex items-center justify-center text-xs font-bold shrink-0"
                  style={{ background: index === 0 ? 'var(--chart-primary)' : 'var(--chart-secondary)', color: index === 0 ? '#fff' : 'var(--color-text)' }}
                >
                  {index + 1}
                </span>
                <div className="min-w-0 flex-1">
                  <p className="font-medium text-sm truncate">{item.source}</p>
                  <div className="mt-1 h-1.5 rounded-full overflow-hidden" style={{ background: 'rgba(5,74,41,0.15)' }}>
                    <div
                      className="h-full rounded-full transition-all duration-500"
                      style={{ width: `${pct}%`, background: index === 0 ? 'var(--chart-primary)' : 'var(--chart-secondary)' }}
                    />
                  </div>
                </div>
                <span className="text-sm font-semibold tabular-nums shrink-0">
                  {Number(item.tco2e).toFixed(3)} t
                </span>
              </li>
            );
          })}
          {sorted.length === 0 && (
            <li className="text-sm opacity-70 py-4" style={{ color: 'var(--color-text)' }}>
              No activity data yet.
            </li>
          )}
        </ul>
      )}
    </div>
  );
}
