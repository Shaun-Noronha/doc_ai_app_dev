import {
  PieChart,
  Pie,
  Cell,
  Tooltip,
  ResponsiveContainer,
} from 'recharts';
import type { ScopeEmission } from '../types';

const COLORS = ['#054A29', '#96E072', '#5a9c4a'];
const RADIAN = Math.PI / 180;

interface Props {
  data: ScopeEmission[];
  loading?: boolean;
}

const CustomTooltip = ({ active, payload }: any) => {
  if (active && payload?.length) {
    const d = payload[0].payload as ScopeEmission;
    return (
      <div
        className="rounded-xl px-4 py-3 text-sm shadow-xl"
        style={{
          background: '#054A29',
          color: '#fff',
          border: '1px solid rgba(255,255,255,0.2)',
        }}
      >
        <p className="font-semibold mb-1">{d.label}</p>
        <p style={{ color: '#96E072' }} className="font-bold">{Number(d.tco2e).toFixed(3)} tCO₂e</p>
      </div>
    );
  }
  return null;
};

const renderSliceLabel = ({ cx, cy, midAngle, innerRadius, outerRadius, percent }: any) => {
  if (percent < 0.05) return null;
  const radius = innerRadius + (outerRadius - innerRadius) * 0.55;
  const x = cx + radius * Math.cos(-midAngle * RADIAN);
  const y = cy + radius * Math.sin(-midAngle * RADIAN);
  return (
    <text x={x} y={y} fill="white" textAnchor="middle" dominantBaseline="central"
      fontSize={13} fontWeight={600} style={{ pointerEvents: 'none' }}>
      {`${(percent * 100).toFixed(0)}%`}
    </text>
  );
};

export default function ScopeDonut({ data, loading }: Props) {
  const total = data.reduce((s, d) => s + d.tco2e, 0);

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
          GHG Emissions by Scope
        </h3>
        <p className="text-xs mt-0.5 opacity-80" style={{ color: 'var(--color-text)' }}>
          Total:{' '}
          <span className="font-bold">
            {total.toLocaleString(undefined, { maximumFractionDigits: 2 })} tCO₂e
          </span>
        </p>
      </div>

      {loading ? (
        <div className="flex-1 flex items-center justify-center">
          <div className="w-40 h-40 rounded-full border-8 border-slate-200 border-t-emerald-500 animate-spin" />
        </div>
      ) : (
        /* Relative container for chart + center label overlay */
        <div className="flex-1 min-h-[260px] relative">
          <ResponsiveContainer width="100%" height="100%">
            <PieChart>
              <Pie
                data={data}
                cx="50%"
                cy="50%"
                innerRadius="50%"
                outerRadius="76%"
                paddingAngle={3}
                dataKey="tco2e"
                nameKey="label"
                labelLine={false}
                label={renderSliceLabel}
              >
                {data.map((_entry, index) => (
                  <Cell
                    key={`cell-${index}`}
                    fill={COLORS[index % COLORS.length]}
                    stroke="rgba(255,255,255,0.6)"
                    strokeWidth={2}
                  />
                ))}
              </Pie>
              <Tooltip content={<CustomTooltip />} />
            </PieChart>
          </ResponsiveContainer>

          {/* Center label – absolutely positioned over the donut hole */}
          <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
            <div className="text-center leading-tight" style={{ color: 'var(--color-text)' }}>
              <p className="text-xl font-bold tabular-nums">
                {total.toFixed(2)}
              </p>
              <p className="text-[11px] font-medium mt-0.5 opacity-80">tCO₂e</p>
            </div>
          </div>
        </div>
      )}

      {/* Scope breakdown rows – label (with short explanation) + tonne value only */}
      <div className="flex flex-col gap-2.5 pt-3 border-t" style={{ borderColor: 'rgba(5,74,41,0.12)' }}>
        {data.map((d, i) => {
          const scopeLabel =
            d.scope === 'Scope 1'
              ? 'Scope 1 (Direct – fuel burned on-site and in company vehicles)'
              : d.scope === 'Scope 2'
                ? 'Scope 2 (Indirect – purchased electricity, heat, steam, cooling)'
                : d.scope === 'Scope 3'
                  ? 'Scope 3 (Value chain – shipping, waste, business travel, etc.)'
                  : d.label;
          return (
            <div key={d.scope} className="flex items-center justify-between text-xs gap-3" style={{ color: 'var(--color-text)' }}>
              <div className="flex items-center gap-2 min-w-0">
                <span className="w-3 h-3 rounded-full shrink-0" style={{ background: COLORS[i] }} />
                <span className="font-medium">{scopeLabel}</span>
              </div>
              <span className="font-semibold shrink-0 text-right tabular-nums">
                {Number(d.tco2e).toFixed(3)} t
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
