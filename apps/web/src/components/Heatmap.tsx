const RAMP = ["#e8fffb", "#a9e8d8", "#4fbfa6", "#009176", "#004d3e"];
const DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

/** Weekday by hour (UTC). Empty cells had no data and are drawn with a dotted outline, not as zero. */
export function Heatmap({ cells, max, label }: { cells: (number | null)[][]; max: number; label: string }) {
  const cw = 30, ch = 24, ml = 40, mt = 6;
  return (
    <svg viewBox={`0 0 ${ml + 24 * cw + 6} ${mt + 7 * ch + 30}`} width="100%" role="img" aria-label={label}>
      <title>{label}</title>
      {cells.map((row, d) => (
        <g key={DAYS[d]}>
          <text x={ml - 8} y={mt + d * ch + ch / 2 + 4} textAnchor="end" fontSize="11" fill="#393733">{DAYS[d]}</text>
          {row.map((v, h) => {
            const lvl = v === null || max === 0 ? -1 : Math.min(4, Math.floor((v / max) * 4.999));
            return lvl < 0 ? (
              <rect key={h} x={ml + h * cw + 1} y={mt + d * ch + 1} width={cw - 2} height={ch - 2} rx={5} fill="none" stroke="#dfdcd6" strokeDasharray="2 3" />
            ) : (
              <rect key={h} x={ml + h * cw + 1} y={mt + d * ch + 1} width={cw - 2} height={ch - 2} rx={5} fill={RAMP[lvl]}>
                <title>{`${DAYS[d]} ${String(h).padStart(2, "0")}:00 UTC: ${Math.round(v ?? 0).toLocaleString()}`}</title>
              </rect>
            );
          })}
        </g>
      ))}
      {[0, 3, 6, 9, 12, 15, 18, 21].map((h) => (
        <text key={h} x={ml + h * cw + cw / 2} y={mt + 7 * ch + 18} textAnchor="middle" fontSize="11" fill="#393733">{String(h).padStart(2, "0")}</text>
      ))}
    </svg>
  );
}
