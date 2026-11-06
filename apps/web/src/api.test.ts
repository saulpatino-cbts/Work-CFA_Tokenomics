import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, fetchSeries, fetchUsage } from "./api";

const range = { start: new Date("2026-01-01T00:00:00Z"), end: new Date("2026-01-02T00:00:00Z") };

afterEach(() => vi.unstubAllGlobals());

function stub(res: Response) {
  const fetchMock = vi.fn().mockResolvedValue(res);
  vi.stubGlobal("window", { location: { origin: "https://app.test" } });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

describe("api client", () => {
  it("sends the bearer token and repeated group_by params", async () => {
    const f = stub(new Response(JSON.stringify({ series: [] })));
    await fetchSeries("tok", range, "cache_read");
    const [url, init] = f.mock.calls[0] as [URL, RequestInit];
    expect(init.headers).toEqual({ Authorization: "Bearer tok" });
    expect(url.pathname).toBe("/v1/usage/series");
    expect(url.searchParams.get("category")).toBe("cache_read");
    expect(url.searchParams.getAll("group_by")).toEqual(["provider", "sku"]);
    expect(url.searchParams.get("start")).toBe("2026-01-01T00:00:00.000Z");
  });
  it("turns an error status into an ApiError carrying the status", async () => {
    stub(new Response("no", { status: 403 }));
    await expect(fetchUsage("tok", range)).rejects.toMatchObject({ status: 403 });
    stub(new Response("no", { status: 401 }));
    await expect(fetchUsage("tok", range)).rejects.toBeInstanceOf(ApiError);
  });
});
