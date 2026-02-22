import { useEffect, useMemo, useState } from 'react';
import { ResponsiveContainer, BarChart, Bar, XAxis, YAxis, Tooltip } from 'recharts';

const MONTH_LABELS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

interface Point {
  period: string;
  tco2e: number;
}

interface ChartPoint {
  monthLabel: string;
  period: string;
  tco2e: number;
}

interface Props {
  data: Point[];
  loading?: boolean;
}

const CustomTooltip = ({ active, payload }: { active?: boolean; payload?: Array<{ payload: ChartPoint; value: number }> }) => {
  if (!active || !payload?.length) return null;
  const p = payload[0].payload;
  return (
    <div
      className="text-xs rounded-lg px-3 py-2 shadow-lg border"
      style={{ background: 'var(--color-card)', color: 'var(--color-text)', borderColor: 'var(--color-card-outline)' }}
    >
      <p className="font-semibold">{p.period}</p>
      <p className="opacity-90">{Number(payload[0].value).toFixed(3)} tCO₂e</p>
    </div>
  );
};

/** Month-wise tCO₂e: year filter, 3-letter month labels, thin domed bars close together. */
export default function MonthlyTco2BarChart({ data, loading }: Props) {
  const years = useMemo(() => {
    const set = new Set<string>();
    data.forEach((d) => {
      const y = d.period?.slice(0, 4);
      if (y) set.add(y);
    });
    return Array.from(set).sort((a, b) => b.localeCompare(a));
  }, [data]);

  const [selectedYear, setSelectedYear] = useState<string>('');
  useEffect(() => {
    if (years.length && !years.includes(selectedYear)) setSelectedYear(years[0]);
  }, [years, selectedYear]);

  const chartData = useMemo((): ChartPoint[] => {
    return data
      .filter((d) => d.period?.startsWith(selectedYear))
      .sort((a, b) => a.period.localeCompare(b.period))
      .map((d) => {
        const monthNum = parseInt(d.period?.slice(5, 7) || '0', 10);
        const monthLabel = MONTH_LABELS[monthNum - 1] ?? d.period;
        return { monthLabel, period: d.period, tco2e: d.tco2e };
      });
  }, [data, selectedYear]);

  const maxTco2 = chartData.length ? Math.max(...chartData.map((d) => d.tco2e), 0.01) : 1;

  return (
    <div className="rounded-2xl p-5 h-full flex flex-col" style={{ background: 'var(--color-card)', boxShadow: 'var(--shadow-card)' }}>
      <div className="mb-3 flex items-center justify-between gap-4 flex-wrap">
        <div>
          <h3 className="text-sm font-bold uppercase tracking-widest opacity-80" style={{ color: 'var(--color-text)' }}>
            Monthly emissions (tCO₂e)
          </h3>
          <p className="text-xs opacity-70 mt-0.5" style={{ color: 'var(--color-text)' }}>
            Thin bars by month, domed top
          </p>
        </div>
        {years.length > 0 && (
          <label className="flex items-center gap-2">
            <span className="text-xs font-medium opacity-80" style={{ color: 'var(--color-text)' }}>Year</span>
            <select
              value={selectedYear}
              onChange={(e) => setSelectedYear(e.target.value)}
              className="text-sm rounded-lg px-3 py-1.5 border focus:outline-none focus:ring-2"
              style={{ borderColor: 'var(--color-card-outline)', color: 'var(--color-text)', background: 'var(--color-card)' }}
            >
              {years.map((y) => (
                <option key={y} value={y}>{y}</option>
              ))}
            </select>
          </label>
        )}
      </div>
      {loading ? (
        <div className="flex-1 min-h-[240px] rounded-xl animate-pulse" style={{ background: 'var(--color-card-outline)' }} />
      ) : !chartData.length ? (
        <div className="flex-1 min-h-[240px] flex items-center justify-center text-sm opacity-60" style={{ color: 'var(--color-text)' }}>
          No data for {selectedYear || 'this year'}
        </div>
      ) : (
        <ResponsiveContainer width="100%" height={280}>
          <BarChart
            data={chartData}
            margin={{ top: 12, right: 8, left: 0, bottom: 4 }}
            barCategoryGap={4}
          >
            <XAxis
              dataKey="monthLabel"
              tick={{ fontSize: 10, fill: 'var(--color-text)', opacity: 0.8 }}
              tickLine={false}
              axisLine={{ stroke: 'var(--color-card-outline)' }}
            />
            <YAxis
              domain={[0, maxTco2 * 1.05]}
              tick={{ fontSize: 10, fill: 'var(--color-text)', opacity: 0.7 }}
              tickLine={false}
              axisLine={false}
              tickFormatter={(v) => `${v.toFixed(1)}`}
              width={32}
            />
            <Tooltip content={<CustomTooltip />} cursor={{ fill: 'rgba(5, 74, 41, 0.06)' }} />
            <Bar
              dataKey="tco2e"
              fill="var(--chart-primary)"
              radius={[6, 6, 0, 0]}
              barSize={12}
              maxBarSize={24}
            />
          </BarChart>
        </ResponsiveContainer>
      )}
    </div>
  );
}
