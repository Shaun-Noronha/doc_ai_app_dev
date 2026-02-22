import type { ReactNode } from 'react';
import { SparklineChart } from './SparklineChart';
import ProgressRing from './ProgressRing';

interface SparklinePoint {
  period: string;
  tco2e: number;
}

interface Props {
  title: string;
  value: string | number;
  unit?: string;
  subtext?: string;
  icon: ReactNode;
  iconBg: string;
  trend?: 'up' | 'down' | 'neutral';
  trendText?: string;
  sparkline?: SparklinePoint[];
  progressRing?: number;  // 0-100
  loading?: boolean;
}

export default function KpiCard({
  title,
  value,
  unit,
  subtext,
  icon,
  iconBg,
  trend,
  trendText,
  sparkline,
  progressRing,
  loading,
}: Props) {
  const trendColor =
    trend === 'down' ? 'text-emerald-500' : trend === 'up' ? 'text-rose-500' : 'text-slate-400';
  const trendArrow = trend === 'down' ? '↓' : trend === 'up' ? '↑' : '→';

  return (
    <div
      className="kpi-card group relative rounded-2xl p-5 flex flex-col gap-3 transition-all duration-200 hover:-translate-y-1 cursor-default"
      style={{
        background: 'var(--color-card)',
        backdropFilter: 'blur(16px)',
        WebkitBackdropFilter: 'blur(16px)',
        border: '1px solid rgba(255,255,255,0.9)',
        boxShadow: 'var(--shadow-card)',
      }}
    >
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <p className="text-xs font-semibold uppercase tracking-widest text-slate-400">{title}</p>
        </div>
        <div
          className="w-10 h-10 rounded-xl flex items-center justify-center shrink-0 transition-transform duration-200 group-hover:scale-110"
          style={{ background: iconBg }}
        >
          {icon}
        </div>
      </div>

      {/* Main value */}
      {loading ? (
        <div className="h-9 w-28 rounded-lg bg-slate-200 animate-pulse" />
      ) : progressRing != null ? (
        <div className="flex items-center gap-4">
          <ProgressRing value={progressRing} size={72} />
          <div>
            <p className="text-2xl font-bold text-slate-800">{value}<span className="text-base font-semibold ml-1 text-slate-500">{unit}</span></p>
            {subtext && <p className="text-xs text-slate-400 mt-0.5">{subtext}</p>}
          </div>
        </div>
      ) : (
        <div>
          <p className="text-3xl font-bold text-slate-800 leading-none">
            {typeof value === 'number' ? value.toLocaleString(undefined, { maximumFractionDigits: 1 }) : value}
            {unit && <span className="text-base font-semibold ml-1.5 text-slate-500">{unit}</span>}
          </p>
          {subtext && <p className="text-xs text-slate-400 mt-1">{subtext}</p>}
        </div>
      )}

      {/* Sparkline or trend */}
      {sparkline && sparkline.length > 0 && (
        <div className="mt-auto">
          <SparklineChart data={sparkline} />
        </div>
      )}

      {/* Trend label */}
      {trendText && (
        <p className={`text-xs font-medium mt-auto ${trendColor}`}>
          {trendArrow} {trendText}
        </p>
      )}
    </div>
  );
}
