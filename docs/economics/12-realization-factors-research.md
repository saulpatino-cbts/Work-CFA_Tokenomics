# Realization and cashability: research note

**Status:** research note, 2026-11-12. Part of the [AI economics redesign](README.md). It supports working assumption 6 of [ADR 0011](../adr/0011-ai-economics-platform.md) ("no default realization or cashability factors"). Findings come from public web search summaries, mostly vendor and consultancy blogs, and were not checked against primary sources. Every figure below is **[VERIFY]** before any external use.

## Question

Should the product ship a default percentage for how much saved time or avoided cost becomes real money (realization), and how should capacity value (hours freed) be kept apart from cashable value (spend that actually falls)?

## What was found

- **No authoritative default exists.** No FinOps Foundation definition of "capacity" or "cashable" value was found, and no standard benchmark for converting saved hours into financial benefit.
- **Realized versus avoided is a common split.** Sources separate cost that left the invoice (realized savings) from spend that never occurred (cost avoidance), and advise reporting them as separate lines. One source advises agreeing the terms with Finance first, since some finance teams read "savings" as a budget reduction.
- **The only explicit conversion figure is weak.** One enterprise blog says about 41% of AI time savings becomes measurable business value, without naming its research. **[VERIFY]**
- **Direct measurement gives much lower numbers.** A Danish study reported self-estimated savings of about 2.8% of work hours but could not detect any effect on recorded hours or earnings (the authors rule out effects above about 2%). Self-reported savings can far exceed realized gains. **[VERIFY]**
- **Gartner-attributed survey figures** (19% of employees reporting no time saved; 4.8 hours a week for sellers) come from a secondary summary and were not checked. **[VERIFY]**
- **Capacity turns into value only when redeployed or removed.** Sources agree that saved time is worth money when the organization can redeploy it, avoid a hire or overtime, or serve more customers, and is otherwise lost. A simple formula (people x hours x loaded rate x weeks) gives an upper bound, not a forecast.

## Conclusion for this repository

1. **Keep "no default factors."** The research supports the existing rule: a realization or cashability factor must be entered by the user with a written rationale. A shipped default would invent a figure the sources do not support.
2. **Keep capacity and cashable value separate**, as the economics engine does. Cashable value should require evidence that spend falls (an avoided hire, removed overtime, a cancelled contract).
3. **Label every figure by basis** (observed, estimated, assumed). A realization factor is an assumption and the explain view must say so.
4. **Optionally offer reference ranges in help text only**, clearly marked as unverified external claims and never prefilled. This is a product decision for the owner.

## Not found

The FinOps Foundation's own definitions of capacity and cashable benefit; any primary-source benchmark for AI productivity realization. A targeted read of the Foundation's materials on AI value is the next step if a defensible reference range is wanted.
