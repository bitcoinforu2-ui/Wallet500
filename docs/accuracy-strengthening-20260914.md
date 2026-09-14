# Wallet500 Accuracy Strengthening — 2026-09-14

This change is intentionally conservative and fail-closed.

## Locked production invariants

- Real-alert score threshold remains **85.0**.
- Missing or malformed Solana authority data is **UNKNOWN**, never silently treated as revoked/safe.
- Mint authority UNKNOWN or ACTIVE is a production hard block; verified explicit null remains REVOKED.
- Freeze authority UNKNOWN/ACTIVE is surfaced as a security risk signal without silently changing the existing trading threshold.
- Pair-quality ranking considers only exact verified DEX pairs and never token-wide TVL as executable liquidity.
- Acceleration requires strictly increasing, non-future timestamps and normalizes changes by elapsed time.
- Wallet-cluster accumulation is research/ranking shadow evidence only; it cannot create a REAL_ALERT, auto-promote, or auto-buy.
- Full Guard includes these accuracy contracts before merge/deploy.

These contracts are designed to improve precision without loosening the existing alert gates or strategy thresholds.
