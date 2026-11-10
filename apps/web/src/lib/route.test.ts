import { describe, expect, it } from "vitest";
import { applicationHref, parseRoute } from "./route";

const ID = "0f8fad5b-d9cb-469f-a165-70867728950e";

describe("routes", () => {
  it("parses application tabs and defaults to economics", () => {
    expect(parseRoute(`#/applications/${ID}/value`)).toEqual({ page: "application", id: ID, tab: "value" });
    expect(parseRoute(`#/applications/${ID}`)).toEqual({ page: "application", id: ID, tab: "economics" });
    expect(parseRoute(`#/applications/${ID}/nonsense`)).toMatchObject({ tab: "economics" });
    expect(applicationHref(ID, "cost")).toBe(`#/applications/${ID}/cost`);
  });
  it("sends anything unrecognised, including a non-UUID id, to the portfolio", () => {
    for (const h of ["", "#", "#/", "#/applications/../x", "#/applications/123", "#/other"]) expect(parseRoute(h)).toEqual({ page: "portfolio" });
    expect(parseRoute("#/usage")).toEqual({ page: "usage" });
  });
});
