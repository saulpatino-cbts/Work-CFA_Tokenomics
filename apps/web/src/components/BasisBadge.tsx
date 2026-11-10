import type { Basis } from "../types";

// Never colour alone: each basis has its own symbol, wording and border style.
const BASIS: Record<Basis, { symbol: string; label: string; hint: string }> = {
  observed: { symbol: "●", label: "Observed", hint: "Taken from a bill or a measurement" },
  estimated: { symbol: "◐", label: "Estimated", hint: "Calculated from prices or models, not billed" },
  assumed: { symbol: "○", label: "Assumed", hint: "A person's assumption" },
};

export function BasisBadge({ basis }: { basis: Basis }) {
  const b = BASIS[basis];
  return (
    <span className={`basis basis-${basis}`} title={b.hint}>
      <span aria-hidden="true">{b.symbol}</span> {b.label}
    </span>
  );
}
