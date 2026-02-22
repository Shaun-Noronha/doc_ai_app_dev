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
    trend === 'down' ? 'text-[#054A29]' : trend === 'up' ? 'text-rose-500' : 'opacity-70';
  const trendArrow = trend === 'down' ? '↓' : trend === 'up' ? '↑' : '→';

  return (
    <div
      className="kpi-card group relative rounded-2xl p-5 flex flex-col gap-3 transition-all duration-200 hover:-translate-y-1 cursor-default"
      style={{
        background: 'var(--color-card)',
        backdropFilter: 'blur(16px)',
        WebkitBackdropFilter: 'blur(16px)',
        boxShadow: 'var(--shadow-card)',
      }}
    >
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <p className="text-xs font-semibold uppercase tracking-widest opacity-70" style={{ color: 'var(--color-text)' }}>{title}</p>
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
            <p className="text-2xl font-bold" style={{ color: 'var(--color-text)' }}>{value}<span className="text-base font-semibold ml-1 opacity-70" style={{ color: 'var(--color-text)' }}>{unit}</span></p>
            {subtext && <p className="text-xs opacity-70 mt-0.5" style={{ color: 'var(--color-text)' }}>{subtext}</p>}
          </div>
        </div>
      ) : (
        <div>
          <p className="text-3xl font-bold leading-none" style={{ color: 'var(--color-text)' }}>
            {typeof value === 'number' ? value.toLocaleString(undefined, { maximumFractionDigits: 1 }) : value}
            {unit && <span className="text-base font-semibold ml-1.5 opacity-70" style={{ color: 'var(--color-text)' }}>{unit}</span>}
          </p>
          {subtext && <p className="text-xs opacity-70 mt-1" style={{ color: 'var(--color-text)' }}>{subtext}</p>}
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
        <p className={`text-xs font-medium mt-auto ${trendColor}`} style={trendColor === 'opacity-70' ? { color: 'var(--color-text)' } : undefined}>
          {trendArrow} {trendText}
        </p>
      )}
    </div>
  );
}
