import { allocationSummary } from "../api";
import type { AuthClient } from "../auth";
import { formatMoney, formatPercent } from "../lib/format";
import { errorText, useAsync } from "../lib/useAsync";

const REASON: Record<string, string> = {
  tag_missing: "Line has no tag the rules look at",
  tag_unmapped: "Tag value maps to no application",
  tag_without_value: "Tag present without a value",
  driver_missing: "No driver entered for the period",
  driver_zero: "Drivers total zero",
  percent_remainder: "Remainder of a fixed-percent split",
  no_rule: "No rule matched",
};

export function CostView({ auth }: { auth: AuthClient }) {
  const [state] = useAsync(auth, allocationSummary, []);
  if (state.kind === "loading") return <p role="status">Loading…</p>;
  if (state.kind === "error") return <p role="alert">Could not load allocation: {errorText(state.status, state.message)}</p>;
  if (state.data.length === 0)
    return <p className="notice">No cost has been imported yet. Import a FOCUS cost file with the administration command, then run an allocation.</p>;
  return (
    <>
      <p className="note">
        This is allocation coverage for everything imported, not for this application alone: the API does not yet report cost per application. Each currency is shown on its own and never added to another.
      </p>
      {state.data.map((s) => (
        <section className="block" key={s.currency} aria-labelledby={`c-${s.currency}`}>
          <h2 id={`c-${s.currency}`}>{s.currency}</h2>
          <div className="figs">
            <div className="fig"><div className="eyebrow">Total effective cost</div><div className="num">{formatMoney(s.total_effective, s.currency)}</div></div>
            <div className="fig"><div className="eyebrow">Allocated to applications</div><div className="num">{formatMoney(s.allocated_effective, s.currency)}</div></div>
            <div className="fig"><div className="eyebrow">Left unallocated, with a reason</div><div className="num">{formatMoney(s.unallocated_effective, s.currency)}</div></div>
            <div className="fig"><div className="eyebrow">Not yet allocated</div><div className="num">{formatMoney(s.not_yet_allocated_effective, s.currency)}</div></div>
            <div className="fig"><div className="eyebrow">Coverage</div><div className="num">{formatPercent(s.coverage)}</div></div>
          </div>
          {Object.keys(s.unallocated_by_reason).length > 0 && (
            <table>
              <caption className="note">Why cost is unallocated</caption>
              <thead><tr><th scope="col">Reason</th><th scope="col" className="n">Effective cost</th></tr></thead>
              <tbody>
                {Object.entries(s.unallocated_by_reason).map(([k, v]) => (
                  <tr key={k}><th scope="row">{REASON[k] ?? k}</th><td className="n">{formatMoney(v, s.currency)}</td></tr>
                ))}
              </tbody>
            </table>
          )}
          {s.provider_split_lines > 0 && <p className="note">{s.provider_split_lines} line(s) carry the provider's own split allocation; check they are not counted twice with their origin charge.</p>}
        </section>
      ))}
    </>
  );
}
