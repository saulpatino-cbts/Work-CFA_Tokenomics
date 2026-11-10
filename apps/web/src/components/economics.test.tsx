import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { AssumptionBanner, Figure } from "../pages/Economics";
import type { ExplainNode, FigureNode } from "../types";
import { BasisBadge } from "./BasisBadge";
import { ExplainTree } from "./ExplainDrawer";

const fig = (over: Partial<FigureNode> = {}): FigureNode => ({
  id: "b".repeat(16), key: "tca", value: "6970", unit: "money", currency: "USD", status: "ok", note: "", basis: "assumed",
  mix: { observed: "0.1", estimated: "0.04", assumed: "0.86" }, ...over,
});

describe("economics components", () => {
  it("each basis has its own symbol and word, so colour is never the only signal", () => {
    const html = (["observed", "estimated", "assumed"] as const).map((b) => renderToStaticMarkup(<BasisBadge basis={b} />));
    expect(html[0]).toContain("●");
    expect(html[1]).toContain("◐");
    expect(html[2]).toContain("○");
    expect(html.join()).toContain("Assumed");
  });
  it("a figure shows its basis and an explain button labelled with the figure", () => {
    const html = renderToStaticMarkup(<Figure label="Total cost" node={fig()} as="money" onExplain={() => {}} />);
    expect(html).toContain("$6,970");
    expect(html).toContain("Assumed");
    expect(html).toContain('aria-label="Explain Total cost"');
  });
  it("an unknown figure reads 'not reported'", () => {
    const html = renderToStaticMarkup(<Figure label="Total cost" node={fig({ status: "unknown", value: null })} as="money" onExplain={() => {}} />);
    expect(html).toContain("not reported");
    expect(html).not.toContain("$0");
  });
  it("the banner states how much of the figure rests on assumptions, and warns past half", () => {
    const html = renderToStaticMarkup(<AssumptionBanner node={fig()} />);
    expect(html).toContain("86% of the net value shown rests on assumptions");
    expect(html).toContain("notice warn");
    expect(renderToStaticMarkup(<AssumptionBanner node={fig({ mix: { observed: "0.9", estimated: "0.05", assumed: "0.05" } })} />)).not.toContain("warn");
    expect(renderToStaticMarkup(<AssumptionBanner node={undefined} />)).toBe("");
  });
  it("the explain tree reaches the inputs, with formula, basis and source", () => {
    const leaf: ExplainNode = { ...fig({ key: "users", value: "100", unit: "users", currency: null }), id: "c".repeat(16), formula: "input", formula_version: 1, label: "Users", source_ref: "assumption users v1", inputs: [] };
    const root: ExplainNode = { ...fig(), formula: "tca.v1", formula_version: 1, label: "", source_ref: null, inputs: [leaf] };
    const html = renderToStaticMarkup(<ul><ExplainTree node={root} /></ul>);
    expect(html).toContain("Formula tca.v1, version 1");
    expect(html).toContain("source: assumption users v1");
    expect(html).toContain("100 users");
    expect(html).toContain("id " + "c".repeat(16));
  });
});
