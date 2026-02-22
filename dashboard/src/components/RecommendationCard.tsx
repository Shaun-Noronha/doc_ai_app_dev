import type { Recommendation } from '../types';
import { ArrowRight, Zap, TrendingDown, Truck, Lightbulb } from 'lucide-react';

const priorityStyles = {
  high: {
    badge: 'bg-rose-100 text-rose-600 border border-rose-200',
    bar: '#f43f5e',
    label: 'High Priority',
  },
  medium: {
    badge: 'bg-amber-100 text-amber-600 border border-amber-200',
    bar: '#f59e0b',
    label: 'Medium Priority',
  },
  low: {
    badge: 'bg-slate-100 text-slate-500 border border-slate-200',
    bar: '#94a3b8',
    label: 'Low Priority',
  },
};

const categoryIcon = (cat: string) => {
  if (cat.includes('ship') || cat.includes('transport')) return <Truck size={18} />;
  if (cat.includes('electric') || cat.includes('light')) return <Lightbulb size={18} />;
  if (cat.includes('fuel') || cat.includes('stationary')) return <Zap size={18} />;
  return <TrendingDown size={18} />;
};

interface Props {
  rec: Recommendation;
}

export default function RecommendationCard({ rec }: Props) {
  const styles = priorityStyles[rec.priority] ?? priorityStyles.low;

  return (
    <div
      className="group relative rounded-2xl p-5 flex flex-col gap-3 transition-all duration-200 hover:-translate-y-0.5 overflow-hidden"
      style={{
        background: 'var(--color-card)',
        backdropFilter: 'blur(16px)',
        WebkitBackdropFilter: 'blur(16px)',
        border: '1px solid rgba(255,255,255,0.9)',
        boxShadow: 'var(--shadow-card)',
      }}
    >
      {/* Accent bar */}
      <span
        className="absolute top-0 left-0 w-full h-1 rounded-t-2xl"
        style={{ background: styles.bar }}
      />

      {/* Header */}
      <div className="flex items-start justify-between gap-2">
        <div className="flex items-center gap-2.5">
          <div
            className="w-9 h-9 rounded-xl flex items-center justify-center shrink-0"
            style={{ background: styles.bar + '20', color: styles.bar }}
          >
            {categoryIcon(rec.category)}
          </div>
          <h4 className="font-semibold text-slate-800 text-sm leading-snug">{rec.title}</h4>
        </div>
        <span className={`text-xs font-semibold px-2.5 py-1 rounded-full shrink-0 ${styles.badge}`}>
          {styles.label}
        </span>
      </div>

      {/* Description */}
      <p className="text-xs text-slate-500 leading-relaxed">{rec.description}</p>

      {/* CTA */}
      <button className="mt-auto flex items-center gap-1.5 text-xs font-semibold text-emerald-600 hover:text-emerald-700 transition-colors w-fit group/btn">
        View Details
        <ArrowRight size={13} className="transition-transform group-hover/btn:translate-x-0.5" />
      </button>
    </div>
  );
}
