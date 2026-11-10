export type Tab = "economics" | "value" | "cost" | "usage";
export const TABS: { id: Tab; label: string }[] = [
  { id: "economics", label: "Economics" },
  { id: "value", label: "Value model" },
  { id: "cost", label: "Cost and allocation" },
  { id: "usage", label: "Usage and tokens" },
];

export type Route = { page: "portfolio" } | { page: "usage" } | { page: "application"; id: string; tab: Tab };

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

/** Hash routes, so the API can keep serving one static page. Anything unrecognised is the portfolio. */
export function parseRoute(hash: string): Route {
  const parts = hash.replace(/^#\/?/, "").split("/").filter(Boolean);
  if (parts[0] === "usage") return { page: "usage" };
  if (parts[0] === "applications" && parts[1] && UUID.test(parts[1])) {
    const tab = TABS.find((t) => t.id === parts[2])?.id ?? "economics";
    return { page: "application", id: parts[1].toLowerCase(), tab };
  }
  return { page: "portfolio" };
}

export const applicationHref = (id: string, tab: Tab = "economics") => `#/applications/${id}/${tab}`;
