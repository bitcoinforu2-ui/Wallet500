# Wallet500 Genesis Radar — v2 Live Policy

Status: LIVE RESEARCH / PAPER ONLY

Purpose: scan newly created or newly trading coins without contaminating Revival Radar. Revival remains veteran-only and Genesis has its own data, scoring, alerts, learning and paper ledger.

## Decision lifecycle
Every candidate has an explicit alert stage in addition to its score/status:

- `WATCH`: discovered or interesting, but not close enough to action or carrying a hard block.
- `HOT_WATCH`: active-window near miss with meaningful evidence. Typical triggers are Genesis score >=65, at least 2 acceleration signals, or a strong trusted-source catalyst such as Moonshot. HOT_WATCH is internal/research and is never a Telegram buy-style alert.
- `REAL_ALERT`: all critical safety evidence is known and safe, acceleration has passed, and the candidate is in an actionable score band. Hard gates always override source catalysts and score.

The lifecycle is designed to make the engine faster on high-quality near misses without weakening safety.

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

### Solana LP integrity adapter
For Solana candidates that first pass the pre-LP gates, Genesis queries RugCheck's token summary as an additional fail-closed LP evidence source.

- `lpLockedPct >= 95%` with no `danger`/`critical` reported risk can satisfy the LP-integrity gate.
- `lpLockedPct < 95%` fails the LP-integrity gate.
- `danger` or `critical` risk fails the LP-integrity gate even when the reported lock percentage is high.
- Unavailable, malformed or missing LP evidence remains UNKNOWN; it never becomes a pass by timeout/default.
- RugCheck is only one safety input. It cannot override liquidity, holder, concentration, mint, freeze or transfer-control gates.

## Acceleration requirement
At least 3 of 5 acceleration signals, with at least one from the first three:
1. Volume acceleration: 15m run-rate >=2.0x prior comparable run-rate or 30m >=2.5x baseline.
2. Buyer acceleration: unique buyers >=1.5x with buy/sell ratio >=1.20 when unique-buyer truth is available.
3. Holder acceleration: +10% in 30m or +20% in 2h without concentration worsening.
4. Liquidity growth: +10% in 30m or +20% in 2h and <=15% drawdown from liquidity peak.
5. Quality-wallet evidence: >=2 qualified wallets or one high-confidence wallet plus independent organic acceleration.

Provider-derived approximations are labeled. Missing unique-buyer or quality-wallet evidence does not get fabricated.

For diagnosis and replay, the engine also publishes a **7-dimension signal summary**: the five acceleration dimensions plus social/narrative confirmation and trusted-source catalyst. This 7-dimension summary explains why a candidate is strengthening; it does not replace the 3-of-5 acceleration rule required for REAL_ALERT.

## Trusted-source catalyst / Moonshot
Source evidence is a soft accelerator, never a safety bypass. The catalyst bonus is capped at +10 points and the final Genesis score remains capped at 100.

- Moonshot `finalized`: +10.
- Moonshot `new`: +8.
- Moonshot `rising`: +7.
- Moonshot `trending` / `top`: +4 because they are more likely to be retrospective momentum confirmation.
- Birdeye new listing: up to +3 base catalyst.
- DexScreener boost: up to +2 base catalyst.
- Independent cross-source confirmation: +2 per additional confirming source, capped so total source catalyst never exceeds +10.

Direct Moonshot `new`/`finalized` candidates receive the highest snapshot priority, followed by Moonshot rising and multi-source confirmations. This is intended to reduce missed early catalysts such as a token being recognized but delayed behind a generic discovery queue.

## No-chase
- 0–100% from first reliable baseline: NORMAL.
- 100–300%: ELEVATED; only high-quality calls.
- 300–1,000%: EXTENDED; fresh paper entry requires score >=85 and survival evidence.
- 1,000–5,000%: VERY_EXTENDED; watch only by default.
- >5,000%: LATE_NO_CHASE; never open a new paper entry from raw momentum.

## Genesis Score
Base evidence weights remain:
- Safety / tradability: 30
- Organic acceleration: 25
- Holder distribution: 15
- Liquidity survival: 15
- Smart-wallet evidence: 10
- Social / narrative confirmation: 5

Trusted-source catalyst may add up to +10 as a bounded accelerator; final score is capped at 100 and hard gates still override it.

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

## Replay / learning truth
Each tracked token/pair now stores its first signal snapshot and later decision history, including price, market cap, liquidity, score, alert stage, source catalyst, signal count, hard blocks and unresolved research-only gates. Future postmortems can therefore answer what the engine knew at discovery time and exactly which gate delayed promotion, without reconstructing or inventing history after a move.

## Live operation
The live lane runs independently on a staggered 15-minute schedule. Discovery watches Solana, Ethereum and BSC; the initial deep on-chain holder/concentration/mint/LP verification and $5 shadow/verified entry lane is Solana-first. EVM candidates remain watch/research until equivalent safety adapters are proven.

The discovery capacity is deliberately wider than the snapshot/deep-analysis capacity. Snapshot and deep-analysis queues are then prioritized by trusted catalyst and cross-source confirmation rather than raw liquidity alone.

Telegram from this lane is **REAL_ALERT-only**: a message is eligible only when the entry is `VERIFIED_PAPER`, its verified track-record flag is true, and `entry_alert_stage == REAL_ALERT`. HOT_WATCH, SHADOW_PAPER and RESEARCH_ONLY remain internal. Every Telegram alert includes the contract address, DexScreener/pair link, timestamp and an explicit `PAPER ONLY — no automatic real-money buy` warning.
