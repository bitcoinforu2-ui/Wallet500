# Social Precursor Shadow — 2026-09-14

## Purpose

Wallet500 may use social, creator/influencer and catalyst evidence to discover early movement sooner, but this evidence is **research/ranking shadow only**. It cannot create a real alert, make a candidate actionable, auto-promote a candidate or trigger an automatic buy.

The canonical real-alert threshold remains **85**. The production risk gate remains authoritative and receives **zero production-score effect** from social evidence.

## Identity truth

Social evidence is allowed to contribute to the shadow score only when both the candidate and the evidence resolve to the same exact `chain + contract` identity.

Ticker-only, name-only, unresolved or ambiguous evidence is rejected from the score. Wallet500 never converts a ticker/name mention directly into an on-chain contract because tickers collide and social posts are easy to misattribute.

EVM contract addresses are normalized to lowercase. Solana mint identity remains case-sensitive.

## Time truth and replay safety

Every scored row must contain a timezone-aware publication/observation timestamp. Future timestamps are rejected. Duplicate evidence is deduplicated by provider + external event/post id + exact asset identity + feature.

Ordinary social evidence expires after six hours. Mention/engagement velocity is normalized by actual elapsed time instead of raw bucket counts, so a 100-mention increase in ten minutes is not treated like the same increase over twenty minutes.

CoinMarketCal estimated dates are deliberately not treated as literal event timestamps. When `isEstimated=true`, Wallet500 preserves the date as `estimated_window_deadline`/display information and sets `event_time_is_exact=false`; estimated timing does not score as an exact catalyst trigger.

## Shadow features

Supported canonical feature classes are:

- `mention_velocity`
- `creator_convergence`
- `social_dominance`
- `sentiment_shift`
- `social_volume`
- `catalyst_proximity`

The result is bounded to 0–100 for research ranking only and always carries these safety flags:

- `ranking_only=true`
- `research_shadow=true`
- `research_only=true`
- `actionable=false`
- `real_alert_eligible=false`
- `automatic_buy=false`
- `auto_promote=false`
- `production_score_effect=0.0`

## Provider strategy

Wallet500 already has provider-redundancy diagnostics. The social precursor contract complements that layer; it does not fabricate redundancy or replace provider health checks.

Optional provider credentials:

| Provider | Environment variable | Intended evidence | Baseline behavior without key |
| --- | --- | --- | --- |
| LunarCrush | `LUNARCRUSH_API_KEY` | social volume, creator convergence, sentiment/trending | neutral / no positive evidence |
| Santiment | `SANTIMENT_API_KEY` | social volume, dominance, weighted sentiment | neutral / no positive evidence |
| CoinMarketCal v2 | `COINMARKETCAL_API_KEY` | scheduled catalysts/events | neutral / no positive evidence |

No paid provider key is required for Wallet500 to continue operating. Missing credentials never count as positive evidence and never weaken production gates.

Direct Reddit dependency is intentionally not part of this core contract because API access/policy is changing; approved provider or platform integrations can feed the same canonical evidence contract later without changing production policy.

## Production invariant

`src/wallet500/production_risk_gate.py` exposes a `social_precursor_shadow` telemetry field only. Tests assert that adding strong social evidence leaves the production decision, hard blocks, caution reasons and real-alert eligibility unchanged.

`tests/test_social_precursor.py` is part of `scripts/full_guard.py`, making exact identity, no future leakage, dedupe, staleness, elapsed-time normalization, estimated-event handling, optional-provider neutrality and the no-auto-action rule critical contracts.
