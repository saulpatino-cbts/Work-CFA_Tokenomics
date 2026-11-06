import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { Heatmap } from "./Heatmap";
import { LineChart } from "./LineChart";
import { Sparkline } from "./Sparkline";

const H = 3_600_000;

describe("charts", () => {
  it("LineChart draws a labelled hatch region and one polyline per series", () => {
    const html = renderToStaticMarkup(
      <LineChart label="test chart" from={0} to={24 * H} hatchFrom={20 * H}
        series={[{ label: "a", points: [{ t: 0, v: 5 }, { t: H, v: 9 }] }, { label: "b", points: [{ t: 0, v: 1 }, { t: H, v: 2 }] }]} />,
    );
    expect(html).toContain("not yet reported");
    expect(html.match(/<polyline/g)).toHaveLength(2);
    expect(html).toContain('role="img"');
    expect(html).toContain('aria-label="test chart"');
  });
  it("LineChart draws no hatch when everything is reported", () => {
    const html = renderToStaticMarkup(<LineChart label="x" from={0} to={24 * H} hatchFrom={null} series={[]} />);
    expect(html).not.toContain("not yet reported");
  });
  it("Heatmap draws empty cells dotted, not as a zero-valued colour", () => {
    const cells = Array.from({ length: 7 }, () => Array<number | null>(24).fill(null));
    (cells[0] as (number | null)[])[3] = 10;
    const html = renderToStaticMarkup(<Heatmap cells={cells} max={10} label="h" />);
    expect(html.match(/stroke-dasharray="2 3"/g)).toHaveLength(7 * 24 - 1);
    expect(html).toContain("Mon 03:00 UTC: 10");
  });
  it("Sparkline says so instead of drawing a flat line when there is no data", () => {
    expect(renderToStaticMarkup(<Sparkline values={[]} label="s" />)).toContain("no hourly data");
  });
});
