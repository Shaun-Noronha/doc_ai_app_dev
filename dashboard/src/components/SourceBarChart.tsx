import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  Cell,
  ResponsiveContainer,
} from 'recharts';
import type { SourceEmission } from '../types';

const SCOPE_COLORS: Record<number, string> = {
  1: '#f59e0b',
  2: '#0ea5e9',
  3: '#8b5cf6',
};

interface Props {
  data: SourceEmission[];
  loading?: boolean;
}

const CustomTooltip = ({ active, payload, label }: any) => {
  if (active && payload?.length) {
    return (
      <div
        className="rounded-xl px-4 py-3 text-sm shadow-xl"
        style={{
          background: 'rgba(15,23,42,0.92)',
          backdropFilter: 'blur(8px)',
          color: '#fff',
          border: '1px solid rgba(255,255,255,0.12)',
        }}
      >
        <p className="font-semibold mb-1">{label}</p>
        <p style={{ color: '#34d399' }} className="font-bold">
          {Number(payload[0].value).toFixed(3)} tCO₂e
        </p>
        <p className="text-slate-400 text-xs mt-1">Scope {payload[0].payload.scope}</p>
      </div>
    );
  }
  return null;
};

export default function SourceBarChart({ data, loading }: Props) {
  return (
    <div
      className="rounded-2xl p-6 flex flex-col gap-4 h-full"
      style={{
        background: 'var(--color-card)',
        backdropFilter: 'blur(16px)',
        WebkitBackdropFilter: 'blur(16px)',
        border: '1px solid rgba(255,255,255,0.9)',
        boxShadow: 'var(--shadow-card)',
      }}
    >
      <div>
        <h3 className="text-sm font-semibold uppercase tracking-widest text-slate-400">Emissions by Source</h3>
        <p className="text-xs text-slate-400 mt-0.5">tCO₂e per emission source</p>
      </div>

      {/* Scope legend */}
      <div className="flex items-center gap-4">
        {[1, 2, 3].map((scope) => (
          <div key={scope} className="flex items-center gap-1.5 text-xs text-slate-500">
            <span className="w-2.5 h-2.5 rounded-sm" style={{ background: SCOPE_COLORS[scope] }} />
            Scope {scope}
          </div>
        ))}
      </div>

      {loading ? (
        <div className="flex-1 flex flex-col gap-3 justify-center">
          {[...Array(5)].map((_, i) => (
            <div key={i} className="flex items-center gap-3">
              <div className="w-24 h-3 bg-slate-200 rounded animate-pulse" />
              <div className="h-6 bg-slate-200 rounded animate-pulse" style={{ width: `${60 - i * 10}%` }} />
            </div>
          ))}
        </div>
      ) : (
        <div className="flex-1 min-h-[280px]">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart
              layout="vertical"
              data={data}
              margin={{ top: 0, right: 24, left: 0, bottom: 0 }}
            >
              <XAxis
                type="number"
                tick={{ fontSize: 11, fill: '#94a3b8' }}
                axisLine={false}
                tickLine={false}
                tickFormatter={(v) => v.toFixed(2)}
              />
              <YAxis
                type="category"
                dataKey="source"
                width={110}
                tick={{ fontSize: 12, fill: '#475569', fontWeight: 500 }}
                axisLine={false}
                tickLine={false}
              />
              <Tooltip content={<CustomTooltip />} cursor={{ fill: 'rgba(15,23,42,0.04)' }} />
              <Bar dataKey="tco2e" radius={[0, 6, 6, 0]} maxBarSize={28}>
                {data.map((entry, index) => (
                  <Cell
                    key={`cell-${index}`}
                    fill={SCOPE_COLORS[entry.scope] ?? '#059669'}
                  />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  );
}
