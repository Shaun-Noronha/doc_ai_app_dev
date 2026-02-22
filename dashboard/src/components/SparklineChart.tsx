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
      <div className="text-xs rounded-lg px-2 py-1 shadow-lg" style={{ background: '#054A29', color: '#fff' }}>
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
        <Tooltip content={<CustomTooltip />} />
        <Area
          type="monotone"
          dataKey="tco2e"
          stroke="#054A29"
          strokeWidth={2}
          fill="rgba(150,224,114,0.35)"
          dot={false}
          activeDot={{ r: 3, fill: '#054A29', stroke: '#fff', strokeWidth: 2 }}
        />
      </AreaChart>
    </ResponsiveContainer>
  );
}
