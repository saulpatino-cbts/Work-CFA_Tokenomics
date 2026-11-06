import { niceMax } from "../lib/transform";
import { SERIES_STYLES } from "./palette";

export interface ChartSeries {
  label: string;
  points: { t: number; v: number }[];
}

const W = 840, H = 300, ML = 56, MR = 20, MT = 14, MB = 30;

function Marker({ kind, x, y, c }: { kind: string; x: number; y: number; c: string }) {
  const p = { fill: c, stroke: "#012639", strokeWidth: 1 };
  if (kind === "square") return <rect x={x - 3.5} y={y - 3.5} width={7} height={7} {...p} />;
  if (kind === "tri") return <path d={`M${x},${y - 4.5} L${x + 4.5},${y + 3.5} L${x - 4.5},${y + 3.5} Z`} {...p} />;
  if (kind === "diamond") return <path d={`M${x},${y - 5} L${x + 5},${y} L${x},${y + 5} L${x - 5},${y} Z`} {...p} />;
  return <circle cx={x} cy={y} r={3.6} {...p} />;
}

/** Hourly lines. `hatchFrom` shades the period sources have not reported yet; nothing is drawn there. */
export function LineChart({ series, from, to, hatchFrom, label }: {
  series: ChartSeries[]; from: number; to: number; hatchFrom?: number | null; label: string;
}) {
  const iw = W - ML - MR, ih = H - MT - MB;
  const top = niceMax(Math.max(0, ...series.flatMap((s) => s.points.map((p) => p.v))));
  const X = (t: number) => ML + (iw * (t - from)) / (to - from);
  const Y = (v: number) => MT + ih * (1 - v / top);
  const hours = Math.round((to - from) / 3_600_000);
  const step = hours <= 30 ? 3 : 24;
  const ticks: number[] = [];
  for (let h = 0; h <= hours; h += step) ticks.push(from + h * 3_600_000);
  const fmt = (t: number) => {
    const d = new Date(t);
    return step === 3 ? `${String(d.getUTCHours()).padStart(2, "0")}:00` : `${d.getUTCMonth() + 1}/${d.getUTCDate()}`;
  };
  return (
    <svg viewBox={`0 0 ${W} ${H}`} width="100%" role="img" aria-label={label}>
      <title>{label}</title>
      <defs>
        <pattern id="hatch" width="7" height="7" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
          <line x1="0" y1="0" x2="0" y2="7" stroke="#393733" strokeWidth="1" />
        </pattern>
      </defs>
      {[0, 0.25, 0.5, 0.75, 1].map((f) => (
        <g key={f}>
          <line x1={ML} x2={W - MR} y1={Y(top * f)} y2={Y(top * f)} stroke="#dfdcd6" />
          <text x={ML - 8} y={Y(top * f) + 4} textAnchor="end" fontSize="11" fill="#393733">{Math.round(top * f).toLocaleString()}</text>
        </g>
      ))}
      {ticks.map((t) => (
        <text key={t} x={X(t)} y={H - 8} textAnchor="middle" fontSize="11" fill="#393733">{fmt(t)}</text>
      ))}
      {hatchFrom != null && hatchFrom < to && (
        <g>
          <rect x={X(Math.max(hatchFrom, from))} y={MT} width={W - MR - X(Math.max(hatchFrom, from))} height={ih} fill="url(#hatch)" opacity=".18" />
          <text x={(X(Math.max(hatchFrom, from)) + W - MR) / 2} y={MT + 14} textAnchor="middle" fontSize="11" fontWeight="700">not yet reported</text>
        </g>
      )}
      {series.map((s, i) => {
        const st = SERIES_STYLES[i % SERIES_STYLES.length]!;
        const pts = s.points.map((p) => `${X(p.t).toFixed(1)},${Y(p.v).toFixed(1)}`).join(" ");
        return (
          <g key={s.label}>
            <polyline points={pts} fill="none" stroke={st.color} strokeWidth={3} strokeDasharray={st.dash} />
            {s.points.filter((_, k) => k % 4 === 0).map((p) => (
              <Marker key={p.t} kind={st.marker} x={X(p.t)} y={Y(p.v)} c={st.color} />
            ))}
          </g>
        );
      })}
    </svg>
  );
}

export function Legend({ labels }: { labels: string[] }) {
  return (
    <div className="legend">
      {labels.map((l, i) => {
        const st = SERIES_STYLES[i % SERIES_STYLES.length]!;
        return (
          <span className="lg" key={l}>
            <svg width="34" height="12" aria-hidden="true"><line x1="0" x2="34" y1="6" y2="6" stroke={st.color} strokeWidth="3" strokeDasharray={st.dash} /></svg>
            {l}
          </span>
        );
      })}
    </div>
  );
}
