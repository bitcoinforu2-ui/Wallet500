# Composite Strong Decision — Shadow Research Only

## Purpose
Evaluate whether veteran-revival candidates that fail only `STRONG_DECISION_LANE` can earn a **shadow-only** composite decision signal from independent evidence without weakening any production REAL_ALERT gate.

## Production safety contract
- `production_change = false`
- `automatic_buy = false`
- REAL_ALERT logic remains unchanged.
- Exact token identity, exact execution pair, veteran age, execution liquidity and risk gates remain mandatory.
- Historical evidence from a different pool MUST NOT be treated as exact-pair execution evidence.

## Shadow hypothesis
A candidate may be tagged `COMPOSITE_STRONG_DECISION_SHADOW` only when all of the following are true:
1. Existing production readiness is exactly 6/7 and the only missing gate is `STRONG_DECISION_LANE`.
2. At least two positive independent evidence lanes are present.
3. One of those positive lanes is holder/wallet evidence (`HOLDER_GROWTH` or verified wallet accumulation).
4. A verified CEX revival lane exists with `cex_revival_score >= 35` and at least 2 coherent confirmations, OR a verified waking/revival market-structure lane exists.
5. Exact execution pair liquidity is verified and passes the canonical production minimum.
6. Risk is clear.
7. Pair provenance is reconciled: token-level evidence may aggregate across venues/pools, but no historical alternate-pair observation can satisfy an exact-pair gate for the current execution pair.

## RAY test case
Token: `4k3Dyjzvzp8eMZWUXbBCjEvwSkkk59S5iCNLY3QrkX6R`
Current execution pair: `6UmmUiYoBjSrhakAobJw8BvkmJtDVxaeBtbt7rxWo1mg`
Historical precursor / wallet pair observed in existing ledgers: `2AXXcN6oN9bBT5owwmTH53C7QHUXvhLeu718Kqt8rvY2`

Current evidence shows:
- readiness 6/7; only `STRONG_DECISION_LANE` missing;
- positive lanes: `HOLDER_GROWTH`, `VERIFIED_SOCIAL`;
- CEX revival evidence for RAY is strong and cross-venue;
- exact execution liquidity on the current pair is verified and deep;
- precursor state remains `INSUFFICIENT_PRECURSOR_EVIDENCE` and references a different historical pair.

Therefore RAY is suitable for **shadow evaluation only**, not production promotion.

## Evaluation rule
Record forward outcomes from the moment the shadow tag is first produced. Compare against matched 6/7 controls that do not satisfy the composite rule. Do not backfill a shadow trigger from later-known evidence. Promote this hypothesis to code only after credible forward evidence and false-positive review.
