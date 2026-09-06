# Wallet500 Genesis Radar — v1 Policy

Status: RESEARCH / PAPER ONLY

Purpose: track newly created or newly trading coins without contaminating the Revival Radar, which remains dedicated to older coins.

## Hard separation
- Revival Radar remains unchanged and continues to reject young pairs according to its own policy.
- Genesis Radar is a separate research pipeline, dataset, scoring model, alerts namespace, and paper portfolio.
- Genesis candidates MUST NOT be counted as Revival calls, winners, alerts, or track-record results.

## Age buckets
- 0–15 minutes: DISCOVERY ONLY. Never alert BUY.
- 15–60 minutes: EARLY WATCH. Can collect evidence; never promote to executable paper call unless all safety gates are verified.
- 1–6 hours: PRIME GENESIS WINDOW.
- 6–24 hours: LATE GENESIS WINDOW.
- 1–7 days: POST-GENESIS / SURVIVAL STUDY.
- >7 days: no longer Genesis; may later become eligible for other pipelines under their own rules.

## Mandatory safety gates (all must pass)
A candidate is blocked if any mandatory gate fails or is unknown.

1. Liquidity
   - Minimum executable liquidity: $50,000.
   - Preferred: >= $100,000.
   - < $50,000 => BLOCKED_LOW_LIQUIDITY.

2. Holder count
   - Minimum: 250 holders.
   - Preferred: >= 500 holders.

3. Concentration
   - Top 10 holders excluding verified LP/burn/treasury: <= 35% preferred, <= 50% hard maximum.
   - Largest non-system wallet: <= 8% preferred, <= 12% hard maximum.
   - Above hard maximum => BLOCKED_CONCENTRATION.

4. Token controls / ownership
   - Mint authority must be revoked/disabled or otherwise proven non-inflationary.
   - Freeze authority must be revoked/disabled when applicable.
   - Honeypot / transfer restrictions / blacklist behavior => BLOCKED.
   - Unknown critical control state => RESEARCH_ONLY.

5. Liquidity integrity
   - LP must be locked/burned/otherwise verifiably non-ruggable, or the venue/pool design must make withdrawal risk inapplicable.
   - Unknown LP ownership or creator-controlled removable liquidity => RESEARCH_ONLY or BLOCKED depending on risk.

## Momentum / acceleration gates
Genesis does not chase raw percentage gain. It looks for acceleration with survival.

A candidate needs at least 3 of the following 5 signals, and at least one must be from the first three:

1. Volume acceleration
   - 15m volume >= 2.0x prior 15m volume, OR
   - 30m volume >= 2.5x comparable recent baseline.

2. Unique buyer acceleration
   - unique buyers 15m >= 1.5x prior 15m,
   - and buy/sell transaction ratio >= 1.20.

3. Holder acceleration
   - holders +10% in 30m OR +20% in 2h,
   - with no matching rise in top-holder concentration.

4. Liquidity growth
   - liquidity +10% in 30m or +20% in 2h,
   - and liquidity does not fall >15% from the local peak after the impulse.

5. Smart-wallet / quality-wallet participation
   - >=2 independently scored quality wallets buying,
   - or >=1 high-confidence wallet plus independent organic acceleration evidence.

## No-chase / extension gate
The system must not promote a coin simply because it has already exploded.

- +0% to +100% from first reliable baseline: normal.
- +100% to +300%: allowed only with score >=75 and all safety gates.
- +300% to +1,000%: EXTENDED; paper call allowed only with score >=85, strong liquidity, holder growth, and retrace/hold confirmation.
- +1,000% to +5,000%: VERY_EXTENDED; watch only by default.
- > +5,000%: LATE / NO_CHASE. Never create a fresh Genesis BUY paper call from raw momentum alone.

A retrace may reset extension status only when price consolidates and reclaims with fresh volume while liquidity and holders survive.

## Genesis Score v1 (0–100)
- Safety / tradability: 30
- Organic acceleration: 25
- Holder quality & distribution: 15
- Liquidity strength & survival: 15
- Smart-wallet evidence: 10
- Social / narrative confirmation: 5

### Status thresholds
- 0–49: IGNORE
- 50–64: WATCH
- 65–74: EVIDENCE_READY
- 75–84: PAPER_BUY_CANDIDATE
- 85–92: STRONG_GENESIS
- 93–100: EXCEPTIONAL_GENESIS

Hard gates override score. A score can never rescue a failed mandatory safety gate.

## Paper portfolio rules
- Research only; no automatic real-money execution.
- Paper entry size: $10 per qualified Genesis call.
- Only one initial paper entry per token per Genesis episode.
- Track entry, current, peak, drawdown, liquidity survival, holder survival, and time-to-2x.
- Suggested evaluation checkpoints: 15m, 30m, 1h, 2h, 6h, 12h, 24h, 3d, 7d.
- Suggested paper exits for study:
  - at +100%: mark 50% hypothetical take-profit;
  - remainder tracked until invalidation, 7d, or configured trailing rule.

## Alert policy
Alerts must clearly say GENESIS and NEW.

- WATCH: dashboard only.
- EVIDENCE_READY: dashboard + optional quiet Telegram research alert.
- PAPER_BUY_CANDIDATE or higher: Telegram research alert with timestamp, pair link, age, score, liquidity, holders, concentration, acceleration evidence, and risk flags.
- Any alert produced after the asset has already moved >5,000% from baseline must be labeled LATE / NO_CHASE, not BUY.

## Learning objective
The first goal is not to maximize the number of calls. It is to answer, across a statistically meaningful sample, whether the engine can identify durable new-coin acceleration before the largest part of the move, while filtering rugs, fake liquidity, concentrated supply, and already-overextended pumps.
