import { useEffect, useRef, useState } from "react";
import { formatCount, formatMoney } from "../lib/format";
import type { ExplainNode } from "../types";
import { BasisBadge } from "./BasisBadge";

function valueText(n: ExplainNode): string {
  if (n.status === "unknown") return "not reported";
  if (n.status === "not_reached") return "not reached";
  if (n.status === "infeasible") return "not feasible";
  if (n.currency && n.unit.startsWith("money")) return formatMoney(n.value, n.currency);
  return `${formatCount(n.value)} ${n.unit}`.trim();
}

/** The calculation behind a figure, down to its inputs. Pure, so it can be tested without a browser. */
export function ExplainTree({ node }: { node: ExplainNode }) {
  const leaf = node.inputs.length === 0;
  return (
    <li>
      <div className="ex-row">
        <strong>{node.label || node.key}</strong> <span className="ex-val">{valueText(node)}</span> <BasisBadge basis={node.basis} />
      </div>
      <div className="note">
        {leaf ? "Input" : `Formula ${node.formula}, version ${node.formula_version}`}
        {node.source_ref ? ` · source: ${node.source_ref}` : ""}
        {node.note ? ` · ${node.note}` : ""}
        <span className="ex-id"> · id {node.id}</span>
      </div>
      {!leaf && (
        <ul className="ex-tree">
          {node.inputs.map((c, i) => (
            <ExplainTree key={`${c.id}-${i}`} node={c} />
          ))}
        </ul>
      )}
    </li>
  );
}

export function ExplainDrawer({ title, load, onClose }: { title: string; load: () => Promise<ExplainNode>; onClose: () => void }) {
  const [state, setState] = useState<{ kind: "loading" } | { kind: "error"; message: string } | { kind: "ready"; node: ExplainNode }>({ kind: "loading" });
  const close = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    let live = true;
    load().then(
      (node) => live && setState({ kind: "ready", node }),
      (e: unknown) => live && setState({ kind: "error", message: e instanceof Error ? e.message : "Request failed" }),
    );
    return () => {
      live = false;
    };
  }, [load]);

  useEffect(() => {
    const before = document.activeElement as HTMLElement | null;
    close.current?.focus();
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("keydown", onKey);
      before?.focus();
    };
  }, [onClose]);

  return (
    <div className="drawer-wrap">
      <button className="drawer-scrim" aria-label="Close explanation" onClick={onClose} tabIndex={-1} />
      <aside className="drawer" role="dialog" aria-modal="true" aria-label={`How ${title} is calculated`}>
        <div className="top">
          <h2>How {title} is calculated</h2>
          <button ref={close} className="sel" onClick={onClose}>Close</button>
        </div>
        {state.kind === "loading" && <p role="status">Loading…</p>}
        {state.kind === "error" && <p role="alert">Could not load the calculation: {state.message}</p>}
        {state.kind === "ready" && (
          <>
            <p className="note">Each line shows its value, how far to trust it, and where it came from. The id is a content hash: it changes if any input, formula or wording changes.</p>
            <ul className="ex-tree root">
              <ExplainTree node={state.node} />
            </ul>
          </>
        )}
      </aside>
    </div>
  );
}
