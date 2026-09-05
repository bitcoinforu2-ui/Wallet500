# Wallet500 Signal Intelligence V1

## Purpose

Signal Intelligence V1 turns Wallet500 from a point-in-time revival detector into a prospective learning system. It records what the engine knew at first observation (T0), follows the exact token/pair forward, compares future outcomes, and learns which evidence patterns separate winners from losers.

This layer does not perform automatic trades and does not weaken existing hard production gates.

## T0 Signal DNA

For every identifiable veteran-coin candidate, the first observation is immutable. Later runs append bounded observations but never rewrite T0.

Normalized features:

- holder acceleration
- unique-buyer acceleration
- wallet accumulation
- organic/social acceleration
- volume acceleration
- liquidity expansion
- CEX acceleration
- price structure

Missing evidence stays unobserved in the raw evidence fields; it is not presented as a verified zero.

## Revival phase detector

The phase state machine is:

`DEAD -> STIRRING -> WAKING -> ACCELERATING -> BREAKOUT -> DISTRIBUTION`

`STIRRING` and `WAKING` are the early-window states. `DISTRIBUTION` is a risk state and cannot be treated as positive accumulation.

## Wallet intent

Current supported classifications:

- `PROBE_BUY`
- `CONVICTION_BUY`
- `CLUSTER_ACCUMULATION`
- `DISTRIBUTION`
- `UNKNOWN`

Intent is derived only from evidence that is actually present in the current candidate evidence sources.

## Expected value

Each candidate receives research-only estimates for:

- probability of reaching +100%
- probability of reaching +300%
- probability of losing 50%
- scenario expected return
- learning score

Before a model is validated, these values use a deliberately conservative heuristic and are marked low confidence. They are not guarantees or trade instructions.

## Winner / Loser DNA

The engine joins immutable T0 records to the forward $10 REAL ALERT paper cohort. Once outcomes exist it compares feature means for winners and non-winners and reports the largest observed separators.

## Self-learning contract

The model remains shadow-only until there are at least 30 prospective examples. Validation is chronological: approximately 70% train / 30% holdout. The model must improve holdout Brier score versus the base-rate benchmark by at least 0.01, with at least eight holdout observations.

Even after validation:

- it may rank existing eligible REAL ALERTs;
- it may not create a REAL ALERT;
- it may not relax liquidity, identity, age, holder/cluster, survival, manipulation, or other hard gates;
- it may not trigger an automatic buy.

## Missed Winner Laboratory

The laboratory analyzes `rejected-outcome-report.json`, including false-negative winners, major winners, first rejection source, and blocking rules. Its output is diagnostic only. A frequently observed blocking rule is not automatically weakened.

## Fail-closed freshness

Required decision inputs have explicit freshness budgets. If a required input is missing or stale, Signal Intelligence reports `DATA_DEGRADED_FAIL_CLOSED`. The signal alert guard then demotes all otherwise-current REAL ALERT rows to non-actionable research watch rows until healthy data is restored.

## Outputs

- `data/signal-intelligence.json`
- `data/signal-dna-ledger.json`
- enriched `data/real-alerts.json`
- enriched `data/real-alert-10usd-ledger.json`
- enriched `data/real-alert-10usd-summary.json`

The $10 cohort remains paper-only and is still opened only by a successfully delivered new Telegram REAL ALERT after the explicit activation time.
