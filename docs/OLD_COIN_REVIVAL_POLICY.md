# Wallet500 Old-Coin Revival Intelligence Policy

Status: ACTIVE DESIGN POLICY

## Priority
Wallet500 production intelligence prioritizes established-token revival. New-token discovery remains enabled for research, historical tracking and model learning; it must not be treated as equivalent production alpha.

Target allocation: ~80% established/revival intelligence, ~20% new-token research.

## Age lanes
- CORE: token/market age >= 7 days. Eligible for revival monitoring and qualification.
- PREFERRED CORE: age >= 30 days. Higher confidence because a meaningful baseline can be built.
- YOUNG: 48 hours to 7 days. Watch/research by default; production escalation requires exceptional multi-source confirmation.
- NEW: <48 hours. RESEARCH_ONLY. Record discovery price, peak, drawdown, volume, liquidity, wallets and outcomes; do not promote as a normal production call.

If reliable token age is unavailable, CEX listing/history depth and accumulated Wallet500 observations are used as evidence. Unknown age must never be silently assumed old.

## Established-token watch entry
A token enters REVIVAL_WATCH when enough independent evidence indicates a meaningful deviation from its own baseline. Initial scoring features:

1. Price acceleration: +2% or more per scan; stronger at +5%.
2. 24h move: +8% starts momentum context, but is not sufficient alone.
3. Volume acceleration: +8% per scan; stronger at +25%.
4. Volume baseline anomaly: current short-window volume / personal median baseline.
5. Open-interest acceleration: +5% per scan; stronger at +15%.
6. Funding divergence: absolute funding >= 0.05%; extreme around >= 0.30%.
7. Cross-exchange confirmation: minimum 2 exchanges; strong confirmation at 4; exceptional at 6+.
8. Cross-exchange lead/lag dispersion: one venue moving materially before peers is recorded as an early-discovery feature, not automatic rejection.
9. Derivatives turnover: high real turnover adds confidence.
10. Liquidity quality/depth: weak liquidity reduces confidence and increases manipulation risk.
11. Spot confirmation: spot volume/price participation should confirm derivatives when data is available.
12. On-chain confirmation: accumulation, holder/buyer growth, smart-wallet activity and transaction acceleration add confidence when chain data is available.
13. Historical quiet-to-active transition: reward a clean revival from a stable baseline rather than an asset already continuously volatile.
14. Event/context divergence: listings, unlocks, announcements or other events are context; unexplained movement can be especially interesting but must be verified.
15. Pump/dump risk: liquidity removal, buyer collapse, severe reversal and fragile volume/liquidity structure can block qualification.

## Suggested stages
OBSERVE: one weak anomaly. Store only.
REVIVAL_WATCH: score >= 35 with at least two useful features, or a strong single anomaly requiring follow-up.
REVIVAL_BUILDING: score >= 50 and >=2 exchange confirmations with acceleration persisting across observations.
REVIVAL_QUALIFIED: score >= 65, >=2 exchange confirmations, no critical pump/dump gate, and either (price + volume acceleration) or (OI acceleration + price confirmation). Prefer >=4 exchanges.
HIGH_CONVICTION: score >= 80, >=4 confirmations, persistent multi-scan acceleration, liquidity/turnover quality, and at least one independent confirmation from OI/funding/spot/on-chain.

Do not require price already to be +40% or +100%. The objective is to detect the transition early, ideally while price is only several percent into the move.

## Baseline intelligence
For each established symbol build rolling personal baselines from Wallet500 history rather than comparing unlike assets. Keep at least:
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
Existing Wallet500 history is intelligence data and must be reviewed, not discarded. Backtest/label previously observed candidates and user case studies (including large winners and dumps) using only information that was actually available at each historical timestamp. No hindsight feature leakage.

Measure at 5m, 15m, 30m, 1h, 4h, 12h and 24h:
- return from first detection
- maximum favorable excursion
- maximum adverse excursion
- time to peak
- whether score/confirmations increased before the move
- which feature combination appeared first
- false-positive rate by archetype

Threshold changes must be versioned and evaluated against the complete track record, including failures.

## New Token Lab
New-token feeds (DEX discovery, Moonshot and similar sources) remain active as a separate learning lane. They should collect complete outcomes, pump/dump signatures and wallet behavior, but should not consume the same production qualification budget as established revival markets.
