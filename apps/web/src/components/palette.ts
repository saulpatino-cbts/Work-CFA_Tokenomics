// Secondary palette, for charts only (brand guide). Series also differ by dash and marker, never colour alone.
export const SERIES_STYLES = [
  { color: "#feb101", dash: "", marker: "circle" },
  { color: "#00e9bb", dash: "6 3", marker: "square" },
  { color: "#bcf405", dash: "2 3", marker: "tri" },
  { color: "#00fbff", dash: "10 3 2 3", marker: "diamond" },
  { color: "#00fe87", dash: "14 4", marker: "circle" },
  { color: "#fcfe0b", dash: "3 3", marker: "square" },
] as const;
export type SeriesStyle = (typeof SERIES_STYLES)[number];
