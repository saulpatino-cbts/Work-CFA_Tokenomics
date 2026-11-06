import { describe, expect, it } from "vitest";
import { seriesLabel, vendorLabel } from "./labels";

describe("labels", () => {
  it("shows readable names and falls back to the raw id", () => {
    expect(vendorLabel("vertex_ai")).toBe("Google Vertex AI");
    expect(vendorLabel("some_new_vendor")).toBe("some_new_vendor");
    expect(vendorLabel(undefined)).toBe("All vendors");
  });
  it("hides an unknown SKU rather than inventing one", () => {
    const base = { points: [] };
    expect(seriesLabel({ ...base, key: { provider: "bedrock", sku: "unknown", source_type: "cloud_telemetry" } })).toBe("Amazon Bedrock");
    expect(seriesLabel({ ...base, key: { provider: "bedrock", sku: "api_provisioned", source_type: "cloud_telemetry" } })).toBe("Amazon Bedrock · API · provisioned");
  });
});
