import { SKU_LABEL, type Series } from "../types";

// Display names only. The API treats vendor ids as opaque strings; unknown ids show as-is.
// Which vendors are actually supported is decided by adapters, not by this table (ADR 0010).
const VENDOR_LABEL: Record<string, string> = {
  bedrock: "Amazon Bedrock",
  foundry: "Microsoft Foundry",
  vertex_ai: "Google Vertex AI",
  claude_code: "Claude Code",
  openai_codex: "OpenAI Codex",
  perplexity: "Perplexity",
  gemini: "Google Gemini",
  github_copilot: "GitHub Copilot",
  microsoft_copilot: "Microsoft Copilot",
};

export const vendorLabel = (id: string | undefined): string => (id ? (VENDOR_LABEL[id] ?? id) : "All vendors");
export const skuLabel = (sku: string): string => SKU_LABEL[sku] ?? sku;

export function seriesLabel(s: Series): string {
  const sku = s.key.sku && s.key.sku !== "unknown" ? skuLabel(s.key.sku) : null;
  return [vendorLabel(s.key.provider), sku].filter(Boolean).join(" · ");
}
