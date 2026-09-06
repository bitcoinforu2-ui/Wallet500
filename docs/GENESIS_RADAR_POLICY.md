# Wallet500 Genesis Radar — v1 Live Policy

Status: LIVE RESEARCH / PAPER ONLY

Purpose: scan newly created or newly trading coins without contaminating Revival Radar. Revival remains veteran-only and Genesis has its own data, scoring, alerts, learning and paper ledger.

## Age windows
- 0–15m: DISCOVERY_ONLY — never create a paper entry.
- 15–60m: EARLY_WATCH.
- 1–6h: PRIME_GENESIS_WINDOW.
- 6–24h: LATE_GENESIS_WINDOW.
- 1–7d: SURVIVAL_STUDY — track only; no new paper entry by default.
- >7d: OUTSIDE_GENESIS.

## Hard thresholds
A verified candidate requires all critical evidence to be known and safe.

- Liquidity: minimum $50,000; preferred >= $100,000.
- Holders: minimum 250; preferred >= 500.
- Top 10 holders excluding identified LP/system balances: preferred <=35%; hard maximum 50%.
- Largest non-system wallet: preferred <=8%; hard maximum 12%.
- Mint authority: revoked/disabled or proven non-inflationary.
- Freeze authority: revoked/disabled when applicable.
- Transfer restrictions / honeypot / blacklist behavior: must be proven safe.
- LP integrity: must be verified safe for a VERIFIED paper call. Unknown LP integrity remains RESEARCH_ONLY.

Unknown evidence is not silently converted into a pass. Genesis may keep an isolated SHADOW_PAPER observation for learning when observable hard thresholds pass but a non-price critical field such as LP-lock truth is still unresolved. SHADOW_PAPER is never counted as a verified call or production track record.

## Acceleration requirement
At least 3 of 5 signals, with at least one from the first three:
1. Volume acceleration: 15m run-rate >=2.0x prior comparable run-rate or 30m >=2.5x baseline.
2. Buyer acceleration: unique buyers >=1.5x with buy/sell ratio >=1.20 when unique-buyer truth is available.
3. Holder acceleration: +10% in 30m or +20% in 2h without concentration worsening.
4. Liquidity growth: +10% in 30m or +20% in 2h and <=15% drawdown from liquidity peak.
5. Quality-wallet evidence: >=2 qualified wallets or one high-confidence wallet plus independent organic acceleration.

Provider-derived approximations are labeled. Missing unique-buyer or quality-wallet evidence does not get fabricated.

## No-chase
- 0–100% from first reliable baseline: NORMAL.
- 100–300%: ELEVATED; only high-quality calls.
- 300–1,000%: EXTENDED; fresh paper entry requires score >=85 and survival evidence.
- 1,000–5,000%: VERY_EXTENDED; watch only by default.
- >5,000%: LATE_NO_CHASE; never open a new paper entry from raw momentum.

## Genesis Score
- Safety / tradability: 30
- Organic acceleration: 25
- Holder distribution: 15
- Liquidity survival: 15
- Smart-wallet evidence: 10
- Social / narrative confirmation: 5

Bands: 0–49 IGNORE, 50–64 WATCH, 65–74 EVIDENCE_READY, 75–84 PAPER_BUY_CANDIDATE, 85–92 STRONG_GENESIS, 93–100 EXCEPTIONAL_GENESIS. Hard gates override score.

## $5 paper portfolio
- Paper entry size is **$5.00**, not $10.
- No automatic real-money execution.
- One initial paper entry per exact token/pair Genesis episode.
- Track entry price, quantity, current value, peak, drawdown, liquidity and holder survival.
- At +100%, mark a hypothetical 50% take-profit at exactly 2x entry and keep the remaining 50% marked to market.
- New entries are limited to the 15m–24h Genesis window.
- VERIFIED_PAPER requires all critical safety gates.
- SHADOW_PAPER is isolated research only, explicitly unverified, and cannot be reported as a verified winner.

## Live operation
The live lane runs independently on a staggered 15-minute schedule. Discovery watches Solana, Ethereum and BSC; the initial deep on-chain holder/concentration/mint verification and $5 shadow/verified entry lane is Solana-first. EVM candidates remain watch/research until equivalent safety adapters are proven.

Telegram messages from this lane must be marked `GENESIS PAPER $5 • NEW`, include an explicit timestamp and pair link, and never look like a production or real-money BUY alert.
