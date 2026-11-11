# 10. Tokenomics vocabulary: the seven-layer stack and Big-T notation

**Status:** proposal. Part of the [AI economics redesign](README.md). The owner pointed to two Tokenomics Foundation publications as the vocabulary FinOps practitioners use for AI cost. This note records what they say, what they do **not** say, and how the product could use them. **Nothing here is built.**

## Read this first: these are not formulas

Both publications were read in full on 2026-11-11 (by a fetch agent, treating page text as data; the figures on both pages are images and were not read). **Neither contains an equation that computes cost.**

- *The Seven-Layer Tokenomics Stack* has no equations. Its only notation is the Big-T labels in a table.
- *Big-T Notation: A Framework for Token Efficiency* (author Dan Neff, Adobe; published by the Tokenomics Foundation) is a **classification of how a workload's token use grows**, borrowed in spirit from Big-O. It says of itself that it "is not a formal mathematical system. There are no proofs and no master theorem", that it "does not measure constants", and that classes are compared "at a stated quality floor".

So neither belongs in the calculation engine as arithmetic. Their value is shared vocabulary and a way to describe risk.

## The seven layers (as published)

Layers rest on one another: "the order is load bearing". Governance, identity, observability and cost management cut across all seven. The stack covers generating and consuming AI; value and pricing decisions are addressed separately, and the token is "the unit of account, not the object of study".

| Layer | Name | Moves the token multiplier? (as published) |
| --- | --- | --- |
| L0 | Energy | No: sets the price and supply of power. Key metrics include energy per token and PUE. |
| L1 | Physical infrastructure | No: sets cost per token. Key metrics include dollars per token and performance per watt. |
| L2 | Infrastructure management | No: sets effective cost per token. |
| L3 | Inference stack | Yes, toward `T(1)` and `T(log n)`. |
| L4 | Model management and selection | Yes, `T(n·k)` toward `T(n)`. |
| L5 | AI access and control | Yes, bounds `T(n·k·a)` and `T(∞)`. |
| L6 | Demand and entry points | Yes: sets the class a workload requires. |

The page adds a caution that matters for us: energy per token is "a rate, valid within one serving configuration, not a comparison across models or environments".

## Big-T classes (as published)

| Class | Name | Meaning in the paper |
| --- | --- | --- |
| `T(1)` | Constant | Token use does not grow with the problem. |
| `T(log n)` | Sublinear | |
| `T(n)` | Linear | |
| `T(n·k)` | Multiplicative | `k` is "often invisible": for example calls, turns or reasoning per request. |
| `T(n·k·a)` | Agent-multiplicative | `a` is agent tree depth. |
| `T(∞)` | Unbounded | |

`n` "covers two things": how many requests and the size of each, and is "deliberately loose". The paper's stance is that the **class is an architecture decision** while "constants are bounded and reversible while growth is neither".

Illustrative figures quoted in the paper (it gives no citations for them, so treat them as claims to check, not facts): a clinical-data example reducing about 240,000 tokens to 19,000 before the model call; a tool-catalog change from 30 tools and 5 turns to 1 and 1; price spreads of 5 to 20 times across model tiers in one generation; per-user consumption rising "a hundredfold or more" at the agent stage.

## How the product could use them (proposals, none built)

1. **A layer map for data sources.** Placing each source on the stack would show what the product can and cannot see.

   | Layer | What this product reads today |
   | --- | --- |
   | L0 Energy | Nothing: billing data does not carry energy. |
   | L1 and L2 | Cloud cost lines (FOCUS exports): cost per resource and per SKU. |
   | L3 Inference | Token and model cost from FOCUS rows and provider telemetry ([`/v1/cost/ai-tokens`](08-focus-1-5-readiness.md), the usage ledger). |
   | L4 Model selection | Model identity and mix per application (scenario model lines). |
   | L5 Access and control | Gateway telemetry, not yet connected; nothing else. |
   | L6 Demand | Application drivers: users, adoption, interactions, transactions. |

   This table is our interpretation of the published layers, not part of either publication.
2. **A Big-T class as a descriptive tag on an application**, set by a person with a rationale and never used in a calculation: an optional field, shown beside the cost figures, and an explicit prompt to revisit it when token use per user changes sharply. It would need a decision on whether the product should hold an opinion about architecture at all.
3. **Surfacing `k` and `a` as scenario drivers.** The scenario engine already multiplies users, adoption, interactions and tokens per interaction. Adding "model calls per interaction" and "agent depth" as optional drivers would let the tornado chart show how sensitive cost is to the multipliers the paper calls invisible. This changes inputs to the existing arithmetic, not its form, and needs an owner decision and a worked example.

## Open questions for the owner

- Should the product record a Big-T class at all, or keep the vocabulary in documentation?
- Is the Tokenomics Foundation vocabulary the one customers use, and is a link or attribution expected in the UI?
- Are there formulas elsewhere (a companion explainer, the assessment checklist, or the paper's linked material) that were meant? Those pages were linked but not read here.
