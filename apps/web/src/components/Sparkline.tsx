export function Sparkline({ values, label }: { values: number[]; label: string }) {
  const w = 210, h = 44;
  if (values.length < 2) return <div style={{ height: h }} className="note">no hourly data</div>;
  const mx = Math.max(...values) || 1;
  const pts = values.map((v, i) => `${((i * w) / (values.length - 1)).toFixed(1)},${(h - 4 - (v / mx) * (h - 8)).toFixed(1)}`).join(" ");
  return (
    <svg viewBox={`0 0 ${w} ${h}`} width="100%" height={h} role="img" aria-label={label}>
      <title>{label}</title>
      <polyline points={pts} fill="none" stroke="#004d3e" strokeWidth="2.5" />
    </svg>
  );
}
