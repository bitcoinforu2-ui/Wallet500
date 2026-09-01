# Wallet500 — Measurable vs Rest Experiment

{
  "generated_at": "2026-09-01T03:26:25.688682+00:00",
  "method": "MEASURABLE_VS_REST_BIAS_EXPERIMENT_V1",
  "production_change": false,
  "truth_rule": "Do not interpret measurability as alpha until technical/data-coverage bias is separated from market-feature differences.",
  "tracked_total": 24364,
  "measured_now_n": 442,
  "rest_n": 23922,
  "technical_layer": {
    "measured": {
      "n": 442,
      "pair_locked_n": 442,
      "pair_locked_pct": 100.0,
      "earliest_snapshot_available_n": 442,
      "earliest_snapshot_available_pct": 100.0,
      "current_pair_available_n": 442,
      "current_pair_available_pct": 100.0,
      "chains": {
        "bsc": 124,
        "ethereum": 112,
        "solana": 206
      },
      "measurement_statuses": {
        "VERIFIED_EXACT_PAIR": 442
      }
    },
    "rest": {
      "n": 23922,
      "pair_locked_n": 22095,
      "pair_locked_pct": 92.36,
      "earliest_snapshot_available_n": 13587,
      "earliest_snapshot_available_pct": 56.8,
      "current_pair_available_n": 13588,
      "current_pair_available_pct": 56.8,
      "chains": {
        "bsc": 8871,
        "ethereum": 835,
        "solana": 14216
      },
      "measurement_statuses": {
        "AWAITING_EXACT_PAIR_OBSERVATION": 22097,
        "UNKNOWN": 69,
        "LEGACY_UNVERIFIABLE_PAIR": 1756
      }
    },
    "snapshot_coverage_gap_pp": 43.2
  },
  "market_layer_earliest_snapshot_only": {
    "measured": {
      "comparable_n": 442,
      "liquidity_usd_median": 0.08,
      "volume_h1_median": 1586.18,
      "turnover_h1_median": 0.274791,
      "buy_sell_ratio_median": 1.260333,
      "txns_h1_median": 29.5
    },
    "rest": {
      "comparable_n": 13587,
      "liquidity_usd_median": 0.0,
      "volume_h1_median": 1333.56,
      "turnover_h1_median": 5.114196,
      "buy_sell_ratio_median": 1.244898,
      "txns_h1_median": 28.0
    },
    "measured_to_rest_ratios": {
      "liquidity_median_ratio_measured_to_rest": null,
      "volume_median_ratio_measured_to_rest": 1.189433,
      "turnover_median_ratio_measured_to_rest": 0.053731,
      "buy_sell_ratio_median_ratio_measured_to_rest": 1.012399,
      "txns_median_ratio_measured_to_rest": 1.053571
    }
  },
  "interpretation_guard": "Market medians use only each token earliest stored historical observation. Missing-history tokens remain in coverage diagnostics.",
  "status": "ANALYZABLE"
}
