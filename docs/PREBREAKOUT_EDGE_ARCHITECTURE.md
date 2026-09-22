# Wallet500 — Prebreakout Edge Architecture

## Goal

Find promising coins **before a large price expansion**, while keeping the production
FINAL BUY gate fail-closed. Early evidence is a prioritization mechanism, never a
substitute for identity, security, liquidity, current intelligence, or confirmation.

## Implemented in this change

### 1. Forward prebreakout evidence

Genesis now produces a separate `prebreakout` object. It deliberately does not
change the historical `genesis_score` or automatically create a BUY.

Current leading evidence:

- **PRESSURE_BEFORE_PRICE_EXTENSION** — volume/order-flow acceleration while price
  is not yet severely extended.
- **LIQUIDITY_COMMITMENT** — liquidity is growing and has not materially withdrawn
  from its recent peak.
- **BREADTH_WITHOUT_CONCENTRATION** — holders are growing while top-holder
  concentration is flat or falling.
- **QUALITY_BUYER_BREADTH** — only when wallet-quality evidence is explicitly
  verified.
- **BONDING_CURVE_NEAR_GRADUATION** / **LAUNCHPAD_MIGRATION_CONFIRMED** — optional
  launchpad lifecycle evidence when a collector supplies verified fields.
- **CREATOR_HISTORY_POSITIVE** / **FUNDER_GRAPH_POSITIVE** — optional creator/funder
  evidence.
- **BUNDLE_DOMINATED_LAUNCH** / **HIGH_BUNDLE_CONCENTRATION** — negative launch
  quality evidence; a bundle-dominated launch cannot receive prebreakout priority.

Missing optional evidence reduces coverage. It is never converted into a positive
signal.

### 2. Independent source corroboration

Discovery now distinguishes raw source strings from independent provider families.

Examples:

- `moonshot:rising` + `moonshot:new` = 2 raw confirmations, **1 independent family**.
- Moonshot + Birdeye = **2 independent families**.

Genesis prioritizes independent corroboration ahead of reserve/liquidity tie-breaks.
This reduces false confidence from several views of the same upstream provider.

### 3. GENESIS_PREBREAKOUT bridge

A fresh Genesis candidate can enter `unified-dynamic-candidates.json` only when:

- `prebreakout.priority_ready == true`;
- the radar snapshot is no older than 45 minutes;
- exact chain + token + pair are present;
- the candidate is in an early/prime/late Genesis window, not outside Genesis;
- it is not `VERY_EXTENDED` or `LATE_NO_CHASE`;
- no Genesis hard safety blocker exists;
- execution-pool liquidity is at least $15K;
- no `BUNDLE_DOMINATED_LAUNCH` risk exists.

The bridge sets `telegram_policy=FINAL_BUY_ONLY`, requires exact identity/pair,
and requests deep/full intelligence. It does **not** set an automatic BUY.

### 4. Same-run intelligence and bounded critical lane

The Unified Watch Engine reserves at most 10 Genesis prebreakout targets, ordered
by prebreakout score and liquidity. They run after time-sensitive CEX movers but
before ordinary static/research targets, and cannot be truncated by the noncritical
runtime budget.

Free intelligence and cross-domain intelligence explicitly include these targets in
the same run so a good early candidate does not stall simply because its candidate
type was missing from an old whitelist.

### 5. Hot recheck

A Genesis candidate can enter the existing bounded fast-recheck lane when only
market/timing confirmation remains. It cannot use the fast market refresh to repair:

- stale/missing intelligence;
- exact-identity failures;
- hard risk;
- missing FINAL BUY intelligence confluence.

Normal confirmation spacing remains in force, so repeated fast refreshes cannot
fake two independent qualifying scans.

---

## Next sensors to build

These are the highest-value additions discovered during the architecture review.
Each should ship first as forward-only shadow evidence, with outcomes measured
before any production weighting change.

### A. Launchpad Lifecycle Sensor

For Pump.fun, Moonshot, Raydium LaunchLab, Four.meme and future launchpads:

- bonding-curve progress;
- change in progress per minute;
- estimated time to graduation;
- exact migration transaction/instruction;
- first AMM pool initialization;
- first meaningful post-migration liquidity;
- migration-to-tradable latency.

**Rule:** curve progress is only an attention signal. Migration must be verified by
chain/program identity, not inferred from ticker or social posts.

### B. Creator + Funder Graph

Track separately:

- factory/program address;
- creator address;
- originating/funding wallets;
- first funding source;
- shared funders across launches;
- creator/funder prior launches;
- prior rug rate;
- prior launches that survived 1h/6h/24h;
- wallet age and funding-cluster reuse.

A factory address must never be scored as if it were the economic creator.

### C. Buyer Cohort Entropy

Replace simple buyer-count thinking with a verified buyer-cohort model:

- unique buyers;
- first-time-to-token buyers;
- independent funding clusters;
- median wallet age;
- median historical realized PnL;
- smart-wallet overlap;
- buyer concentration;
- repeat-wallet share;
- buy-size entropy;
- common-funder/sybil ratio.

A hundred buys from one funded cluster should not look like a hundred independent
buyers.

### D. Flow-vs-Price Compression

Measure when demand expands faster than price:

```
flow_pressure =
    net_buy_usd_acceleration
  + unique_buyer_acceleration
  + volume_acceleration
  + liquidity_retention

price_response =
    abs(price_change_5m) + abs(price_change_15m)

compression = flow_pressure / max(price_response, epsilon)
```

High compression with healthy liquidity can be a useful lead signal. Large price
movement without breadth is the opposite: possible late/chase or manipulation.

### E. Liquidity Elasticity + Refill

Measure:

- price impact per net-buy dollar;
- liquidity growth after buy bursts;
- LP refill speed after volatility;
- liquidity retained after a local peak;
- migration liquidity versus creator-funded liquidity;
- cross-pool depth, not only the currently selected execution pool.

Prefer demand that is absorbed by persistent/deepening liquidity over demand that
moves price only because the pool is thin.

### F. Pool/Route Appearance

Track first appearance in:

- verified AMM pools;
- major aggregators/routers;
- additional quote assets;
- second/third independent pools;
- cross-venue routes.

A token becoming routable across independent venues can precede broader attention,
but identity must remain contract-based.

### G. Bundle / MEV / Sybil Launch Quality

Negative evidence:

- same-slot clustered buys;
- common funder across early buyers;
- extreme sniper share;
- creator-funded buyer cluster;
- repeated identical sizing/timing;
- bundled supply concentration.

Positive evidence should require independent buyers rather than simply penalizing
all fast early activity.

### H. Source Lead-Lag Scoreboard

For every discovery source, measure forward:

- median lead time to +25%, +50%, +100%;
- precision at 15m / 1h / 6h;
- false-positive rate;
- median adverse excursion before upside;
- survivorship/liquidity failure rate.

Weights should be learned from forward outcomes. Do not permanently prefer a
provider because it found one historical winner.

### I. Relative-Chain Residual

Compare the coin with its chain/native asset at the same timestamps:

- token return minus chain return;
- token volume acceleration minus chain activity change;
- buyer growth while chain is flat/down;
- liquidity inflow relative to chain conditions.

This helps separate token-specific ignition from a broad market beta move.

### J. Cross-pool Ignition Propagation

The engine already watches sibling pools. Extend this to measure sequence:

1. Which pool ignited first?
2. Did volume propagate to larger/deeper pools?
3. Did liquidity follow the volume?
4. Did price stay coherent across pools?
5. Is the move supported by more than one quote asset?

A move that propagates from a small pool to deeper independent pools is different
from a one-pool spike.

---

## Required data contract for every new sensor

Every positive or negative evidence row should carry:

- `chain`
- `token_address`
- `pair_address` when pair-specific
- `event_time`
- `observed_at`
- `provider`
- `source_family`
- `freshness_seconds`
- `verified`
- raw metrics used to derive the score
- explicit `missing` / `unknown` state

Never map missing data to zero when zero has a real market meaning.

## Promotion state machine

```
DISCOVERED
  -> EARLY_EVIDENCE
  -> GENESIS_PREBREAKOUT
  -> FULL_INTELLIGENCE
  -> PRE_BUY
  -> FINAL_BUY
```

Any hard risk can move the candidate to `BLOCKED`. Missing/stale evidence moves it
to `WAIT_FOR_EVIDENCE`, not to a fake negative score.

## Evaluation KPIs

The engine should optimize for more than winner count:

- discovery-to-move lead time;
- PRE-BUY-to-move lead time;
- precision of +25/+50/+100 forward moves;
- median maximum favorable excursion;
- median maximum adverse excursion;
- false BUY rate;
- liquidity-failure/rug rate;
- percentage of later winners discovered but incorrectly blocked;
- percentage of winners never discovered;
- evidence freshness at decision time.

The key question for every future change is:

> Did this add **forward lead time with acceptable precision**, or did it merely
> explain a move after it had already happened?
