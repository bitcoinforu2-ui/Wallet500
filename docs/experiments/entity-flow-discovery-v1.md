# Entity Flow Discovery v1

Status: RESEARCH / PAPER ONLY

## Goal
Discover established-token revival candidates by pivoting from known large entities (CEX custody, market makers, funds and high-quality wallets) into token flows, without treating custodial balances as smart-money ownership.

## Core pipeline
Known entity addresses -> token transfers -> entity-neutral recipient wallets -> token candidates -> independent-wallet corroboration -> exact-pair verification -> >= $50K exact execution-pool liquidity -> holder/cluster fail-closed -> existing Wallet500 revival/decision lanes.

## Required normalization
CEX hot/cold wallets, deposit sweep addresses, DEX routers, bridges, LP contracts and other known custodians are bridge nodes, not evidence of common control. Remove/discount them before cluster-control scoring.

## Research features
- CEX net outflow per token and time window
- independent withdrawal-wallet count
- common non-CEX first-funder/common-funder score
- accumulation acceleration
- wallet historical-quality score
- cross-entity confirmation
- entity-neutral connected supply percentage
- common exit/sweep behavior
- wallet activity synchronization

## Truth rules
- No symbol-only identity.
- No custodial balance interpreted as entity conviction.
- No same-color Bubblemaps cluster interpreted as common ownership without on-chain corroboration.
- No production promotion without Exact Pair identity and >= $50K liquidity on the exact execution pool.
- Holder/Cluster remains Fail-Closed.
- Forward-only/no-hindsight timestamps.
- Immutable research observations.
- Paper-only; no execution.
- This experiment cannot change production thresholds.

## Initial live cases
1. CYBERLEEK — existing research case (`data/case-study-cyberleek.json`).
2. DOGE-1 Satellite — live entity-flow/holder-cluster case (`data/case-study-doge1.json`).

## Success criteria
Measure whether entity-flow observations precede existing revival alerts and later verified exact-pair outcomes. Report precision/recall and false-positive causes separately. Promotion is evidence-gated and requires numerical validation; no threshold weakening is permitted.
