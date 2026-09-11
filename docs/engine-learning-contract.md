# Wallet500 prospective engine learning contract

This layer is observability/research only. It cannot change production thresholds, scoring, portfolio truth, or automatic-buy behavior.

## Hard invariants

- Identity is `chain|token|exact_pair`; symbol fallback and ambiguous pair joins are forbidden.
- First-seen timestamps and frozen evidence are immutable after first stage observation.
- Historical records are never backfilled with later signal evidence.
- Later outcomes may be joined only as research labels from an existing canonical outcome source; this layer invents no winner threshold.
- Failed/unavailable providers never count as positive evidence.
- Smart-money backlog statistics never promote a wallet or alter wallet-quality thresholds.
- Lead-time calculations require canonical timestamps and never move first-seen backward.
- Production liquidity, exact-pair, verification, fail-closed and no-hindsight gates are untouched.

## Outputs

`data/engine-learning-review.json` reports cohort progression, blockers, canonical later outcomes, provider health/redundancy visibility, smart-money history backlog, lead time and readiness for signal attribution.

Attribution is valid only for evidence frozen prospectively at the first observation of a stage. Existing cohort records without frozen evidence remain explicitly unavailable for attribution rather than being reconstructed with hindsight.
