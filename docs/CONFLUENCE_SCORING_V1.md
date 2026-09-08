# Wallet500 Confluence Scoring V1

## Purpose

Confluence V1 is a **research ranking layer**, not a buy engine and not a profit probability. It combines independently sourced evidence only after Wallet500's hard truth contracts are satisfied.

Canonical veteran/revival scope stays fixed:

- verified market age: **90 days minimum**
- verified execution liquidity: **$15,000 minimum**
- exact on-chain token identity
- exact DEX pair
- security / sellability / mintability gates remain fail-closed
- stale required evidence cannot become positive

No positive score may override a hard blocker.

## Static prior weights

| Lane | Weight | Why |
|---|---:|---|
| Wallet Alpha | 22 | Repeated, independent wallet behavior is closest to participant intent; third-party wallet labels/PnL are not accepted as ground truth. |
| Market Microstructure | 18 | Exact-pair activity, persistence, turnover and volume/liquidity structure show whether a revival is actually tradable. |
| Execution Copyability | 14 | A great signal that cannot be copied is not useful. Kept separate from predictive alpha and used as an execution multiplier. |
| Holder Growth | 8 | Broadening ownership can confirm reawakening, but holder-count data is noisy and provider-dependent. |
| Funding / Cluster Independence | 5 | Independent funding origins help distinguish organic multi-wallet activity from coordinated clusters. Missing until verified. |
| Social / Narrative | 9 | Useful as an early accelerator when organic and source-confident; never allowed to override market/security truth. |
| Official Catalyst | 8 | Official exchange/project events can be powerful and independent of momentum, but only with exact identity guard and point-in-time evidence. |
| Independent Confirmation | 7 | Rewards multiple independent signal families rather than one dominant metric. |
| CEX Acceleration | 4 | Useful cross-venue confirmation, but symbol mapping and venue effects make it secondary to exact on-chain truth. |
| Price Anti-Chase | 5 | Rewards early structure and punishes signals that become visible only after the move. |
| **Total** | **100** | Static prior only. |

## Why Wallet Alpha gets the largest weight

The goal is not to copy a profitable address blindly. Wallet500 separates:

1. **Alpha quality** — did the wallet repeatedly act before useful moves?
2. **Copyability** — could a follower realistically execute after latency, fees and slippage?
3. **Independence** — are apparently different wallets funded by the same cluster?

External Smart Money / PnL labels are discovery inputs. Wallet500 must recompute performance from on-chain transactions before a wallet can become `VERIFIED_ALPHA`.

## Missing evidence is not zero

A missing lane is recorded as `available=false` and lowers confidence/coverage. It is not inserted as a zero into observed alpha. This avoids rewarding providers with dense data and punishing a token merely because one source is temporarily unavailable.

Stale evidence behaves more strictly: stale evidence is **never positive**.

## Risk is separate from alpha

Positive evidence and risk are intentionally not collapsed into one opaque score.

Risk penalties:

- late move: up to **-18**
- manipulation: up to **-12**
- holder concentration: up to **-12**
- verified paid promotion: **-5**
- shared funding cluster: up to **-12**
- total soft-risk penalty cap: **40**

Paid promotion and holder concentration can only add risk/context; they can never add positive alpha.

Hard blockers have no cap because they force `priority_score = 0`.

## Scores

`signal_alpha_score`
: Weighted average of **available predictive** lanes. Execution copyability is excluded.

`copyability_score`
: Execution-depth/slippage score. It answers "can this signal realistically be followed?" rather than "will price rise?"

`confidence_pct`
: Sum of effective observed weights. Missing/low-confidence lanes lower this value.

`risk_penalty`
: Separate bounded soft-risk deduction.

`priority_score`
: Ranking score:

```
signal_alpha
× (0.55 + 0.45 × confidence)
× copyability multiplier
− risk penalty
```

A hard blocker forces priority to zero.

## Tiers

- `HIGH_CONFLUENCE`: priority >= 72 and confidence >= 55
- `BUILDING_CONFLUENCE`: priority >= 50 and confidence >= 35
- `LOW_CONFIDENCE`: evidence incomplete or weak
- `BLOCKED`: one or more hard truth blockers

These are research-ranking labels, not trade instructions.

## Learning policy

The V1 weights are a documented static prior. They do not change automatically.

A future learned model may change ranking weights only when:

1. samples were captured point-in-time before outcomes;
2. labels include losses and missed winners, not only successes;
3. train/holdout periods are separated forward in time;
4. the model improves a calibration metric such as Brier score over baseline;
5. sample size is sufficient;
6. hard gates remain immutable;
7. learned weights affect ranking only until separately promoted through governance.

## Next data sources

High priority:

- first-funding / source-of-funds graph
- wallet on-chain PnL ledger with fees, transfers and inventory accounting
- wallet copyability / latency simulation
- point-in-time social author credibility
- exact-pair execution depth at multiple order sizes
- security-provider cross-checks as hard veto evidence

The dashboard must expose the components instead of hiding them behind one "AI score".
