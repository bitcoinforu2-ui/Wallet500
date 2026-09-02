# Wallet500 Old-Coin Revival Intelligence Policy

Status: ACTIVE HARD POLICY

## Mission
Wallet500 production intelligence is 100% focused on established-token revival/reawakening.

New-token discovery is not part of the production search objective. Historical files from older experiments may remain for learning and auditability, but they must never enter the visible Revival radar, qualification lane, alerts, paper entries or production decisions.

## Mandatory age rule
A token is eligible for Wallet500 Revival only when there is verified evidence that it has traded in the market for at least 180 days.

Hard rule:

- VERIFIED MARKET AGE >= 180 DAYS: eligible for Revival analysis.
- VERIFIED MARKET AGE < 180 DAYS: rejected.
- UNKNOWN / AMBIGUOUS AGE: rejected fail-closed.
- Contract creation date alone is not sufficient evidence of market age.

Accepted lower-bound evidence can include:

1. Exact CoinGecko identity with ATH/ATL historical market timestamp proving at least 180 days of market history.
2. Exact DexScreener pair identity with pair creation timestamp proving at least 180 days of market history.
3. Another exact, independently verifiable first-market/first-liquidity/first-trade timestamp approved by the same truth rules.

For CEX-only symbols, symbol text alone is never enough when identity is ambiguous. A CEX symbol must resolve to one unambiguous market identity before age verification can pass.

Every visible candidate must expose:

- `market_age_verified: true`
- `market_age_min_days >= 180`
- `market_age_evidence_at`
- `market_age_evidence_source`

The age gate is fail-closed. If age verification fails, the item is excluded from the visible actionable radar even if its momentum/anomaly score is high.

## Revival objective
The system is not searching for launches. It is searching for a new awakening inside an old market.

A mature token enters Revival observation only when independent evidence indicates a meaningful deviation from its own historical baseline. Initial features include:

1. Price acceleration.
2. 24h momentum context.
3. Volume acceleration and volume-vs-personal-baseline anomaly.
4. Open-interest acceleration.
5. Funding divergence.
6. Cross-exchange confirmation and lead/lag behavior.
7. Real derivatives turnover.
8. Liquidity quality/depth and exact-pair survival.
9. Spot confirmation.
10. On-chain accumulation, holder/buyer growth and smart-wallet activity when available.
11. Historical quiet-to-active transition.
12. Event/context divergence.
13. Pump/dump and liquidity-removal risk.

## Suggested stages
OBSERVE: one weak anomaly. Store only.

REVIVAL_WATCH: mature-age gate passed plus score >= 35 with at least two useful features, or a strong single anomaly requiring follow-up.

REVIVAL_BUILDING: mature-age gate passed plus score >= 50 and >=2 exchange confirmations with acceleration persisting across observations.

REVIVAL_QUALIFIED: mature-age gate passed plus score >= 65, >=2 exchange confirmations, no critical pump/dump gate, and either price+volume acceleration or OI acceleration+price confirmation. Prefer >=4 exchanges.

HIGH_CONVICTION: mature-age gate passed plus score >= 80, >=4 confirmations, persistent multi-scan acceleration, liquidity/turnover quality, and at least one independent confirmation from OI/funding/spot/on-chain.

Do not require price already to be +40% or +100%. The objective is to detect the reawakening transition early, ideally while price is only several percent into the move.

## Baseline intelligence
For every mature symbol build rolling personal baselines rather than comparing unlike assets. Keep at least:

- price returns/volatility
- volume and turnover
- open interest
- funding
- exchange count and venue participation
- dispersion/lead-lag
- liquidity when available
- spot-vs-perpetual behavior
- on-chain activity when available

Use robust median/percentile or MAD/z-score style comparisons once enough history exists. Never fabricate historical baseline values when history was not collected.

## Historical review
Existing Wallet500 history remains intelligence data and must not be deleted merely because it predates this policy. Backtests and case studies may preserve younger assets as historical records, but all current Revival candidate selection and alerts must apply the 180-day gate.

Measure at 5m, 15m, 30m, 1h, 4h, 12h and 24h:

- return from first detection
- maximum favorable excursion
- maximum adverse excursion
- time to peak
- whether score/confirmations increased before the move
- which feature combination appeared first
- false-positive rate by archetype

Threshold changes must be versioned and evaluated against the complete track record, including failures.

## Production truth rule
No item may be labeled as a current Revival candidate unless all of the following are true:

1. Market age is verified at >=180 days.
2. Identity is sufficiently resolved for the lane in which it is shown.
3. Required liquidity/pair/risk gates for that lane are satisfied.
4. Missing evidence is displayed as missing, never silently assumed.

Wallet500 Revival = old market, new awakening.
