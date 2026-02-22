import { ResponsiveContainer, AreaChart, Area, Tooltip } from 'recharts';

interface Point {
  period: string;
  tco2e: number;
}

interface Props {
  data: Point[];
  height?: number;
}

const CustomTooltip = ({ active, payload }: any) => {
  if (active && payload?.length) {
    return (
      <div className="text-xs bg-slate-800 text-white rounded-lg px-2 py-1 shadow-lg">
        <p className="font-semibold">{payload[0].payload.period}</p>
        <p>{Number(payload[0].value).toFixed(3)} tCO₂e</p>
      </div>
    );
  }
  return null;
};

export function SparklineChart({ data, height = 48 }: Props) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <AreaChart data={data} margin={{ top: 4, right: 0, left: 0, bottom: 0 }}>
        <defs>
          <linearGradient id="sparkGrad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="5%" stopColor="#059669" stopOpacity={0.3} />
            <stop offset="95%" stopColor="#059669" stopOpacity={0} />
          </linearGradient>
        </defs>
        <Tooltip content={<CustomTooltip />} />
        <Area
          type="monotone"
          dataKey="tco2e"
          stroke="#059669"
          strokeWidth={2}
          fill="url(#sparkGrad)"
          dot={false}
          activeDot={{ r: 3, fill: '#059669', stroke: '#fff', strokeWidth: 2 }}
        />
      </AreaChart>
    </ResponsiveContainer>
  );
}
