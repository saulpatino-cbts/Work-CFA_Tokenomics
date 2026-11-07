"""Economics calculation library (ADR 0011; docs/economics/05-calculation-engine.md).

Pure and deterministic: no database, clock or randomness. Exact decimals only. Every result is a
``Node`` that records its formula, inputs and basis (observed, estimated, assumed).
"""
