interface Props {
  value: number;   // 0-100
  size?: number;
  strokeWidth?: number;
  color?: string;
}

export default function ProgressRing({
  value,
  size = 72,
  strokeWidth = 7,
  color = '#054A29',
}: Props) {
  const r = (size - strokeWidth) / 2;
  const circumference = 2 * Math.PI * r;
  const filled = ((Math.min(Math.max(value, 0), 100)) / 100) * circumference;

  return (
    <svg width={size} height={size} className="shrink-0" style={{ transform: 'rotate(-90deg)' }}>
      {/* Track */}
      <circle
        cx={size / 2}
        cy={size / 2}
        r={r}
        fill="none"
        stroke="#e2e8f0"
        strokeWidth={strokeWidth}
      />
      {/* Progress */}
      <circle
        cx={size / 2}
        cy={size / 2}
        r={r}
        fill="none"
        stroke={color}
        strokeWidth={strokeWidth}
        strokeLinecap="round"
        strokeDasharray={circumference}
        strokeDashoffset={circumference - filled}
        style={{ transition: 'stroke-dashoffset 0.8s ease' }}
      />
      {/* Center label */}
      <text
        x={size / 2}
        y={size / 2 + 5}
        textAnchor="middle"
        fontSize={size * 0.22}
        fontWeight="700"
        fill="var(--color-text)"
        style={{ transform: `rotate(90deg) translateX(0)`, transformOrigin: `${size / 2}px ${size / 2}px`, fontFamily: 'Inter, sans-serif' }}
      >
        {Math.round(value)}%
      </text>
    </svg>
  );
}
