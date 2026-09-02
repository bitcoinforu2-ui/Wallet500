# Wallet500 Research Decision Engine v1

Status: RESEARCH/ADVISORY ONLY
Production thresholds: UNCHANGED
Truth contract: Exact Pair, Liquidity >= $50K on exact execution pool, Holder/Cluster Fail-Closed, No Hindsight, Paper Only.

## Purpose
Convert research into explicit, reviewable implementation proposals instead of isolated case studies.

## Flow
research finding -> measurable hypothesis -> historical/forward evidence -> impact analysis -> recommendation -> human decision -> shadow implementation -> production approval

## Required evidence per proposal
- hypothesis_id
- source_research_ids
- feature_or_rule
- population_definition
- sample_size
- positive_cases
- negative_cases
- baseline_rate
- candidate_rate
- lift_pct
- precision
- recall
- false_positive_delta
- false_negative_delta
- time_to_signal_delta
- exact_pair_coverage
- holder_cluster_coverage
- forward_only_evidence_count
- lookahead_check
- safety_regression_check

## Recommendation states
- REJECT
- MORE_DATA
- SHADOW_TEST
- APPROVED_CANDIDATE

APPROVED_CANDIDATE never changes production by itself. It means the rule is eligible for an explicit human implementation decision followed by shadow validation.

## Hard approval constraints
A proposal cannot be APPROVED_CANDIDATE when any of the following is true:
- sample_size < 100 unless it is a narrowly scoped deterministic bug fix
- lookahead_check != PASS
- safety_regression_check != PASS
- exact_pair_coverage < 95%
- holder_cluster_coverage < 95% for proposals touching tradability/risk
- proposal weakens Liquidity >= $50K, Exact Pair, Holder/Cluster Fail-Closed, immutable history, No Hindsight, or Paper Only
- evidence is only anecdotal/case-study based

## Suggested decision thresholds
These are advisory defaults, not production rules:
- REJECT: lift <= 0 or false-positive cost materially worsens
- MORE_DATA: sample < 100 or confidence insufficient
- SHADOW_TEST: positive lift >= 10% with safety checks passing
- APPROVED_CANDIDATE: positive lift >= 20%, sample >= 300, forward evidence >= 30, no material safety regression, and false-negative improvement without weakening hard gates

## Case-study role
CYBERLEEK, DOGE-1 and future live cases are hypothesis generators. They cannot directly tune production filters. A repeated pattern becomes eligible only after cohort evidence confirms it.

## Output contract
The engine should publish `data/research-decision-engine.json` containing proposals, evidence metrics, recommendation state, and a concise human decision note.
