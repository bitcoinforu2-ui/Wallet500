# Wallet500 — Measurable vs Rest Experiment

{
  "generated_at": "2026-09-02T07:02:02.017793+00:00",
  "method": "MEASURABLE_VS_REST_BIAS_EXPERIMENT_V1",
  "production_change": false,
  "truth_rule": "Do not interpret measurability as alpha until technical/data-coverage bias is separated from market-feature differences.",
  "tracked_total": 32182,
  "measured_now_n": 342,
  "rest_n": 31840,
  "technical_layer": {
    "measured": {
      "n": 342,
      "pair_locked_n": 342,
      "pair_locked_pct": 100.0,
      "earliest_snapshot_available_n": 342,
      "earliest_snapshot_available_pct": 100.0,
      "current_pair_available_n": 342,
      "current_pair_available_pct": 100.0,
      "chains": {
        "bsc": 114,
        "solana": 141,
        "ethereum": 87
      },
      "measurement_statuses": {
        "VERIFIED_EXACT_PAIR": 342
      }
    },
    "rest": {
      "n": 31840,
      "pair_locked_n": 30016,
      "pair_locked_pct": 94.27,
      "earliest_snapshot_available_n": 21521,
      "earliest_snapshot_available_pct": 67.59,
      "current_pair_available_n": 21522,
      "current_pair_available_pct": 67.59,
      "chains": {
        "bsc": 11543,
        "ethereum": 1059,
        "solana": 19238
      },
      "measurement_statuses": {
        "AWAITING_EXACT_PAIR_OBSERVATION": 29889,
        "UNKNOWN": 69,
        "LEGACY_UNVERIFIABLE_PAIR": 1753,
        "QUARANTINED_NON_EXECUTABLE_PRICE": 129
      }
    },
    "snapshot_coverage_gap_pp": 32.41
  },
  "market_layer_earliest_snapshot_only": {
    "measured": {
      "comparable_n": 342,
      "liquidity_usd_median": 3080.825,
      "volume_h1_median": 2593.405,
      "turnover_h1_median": 0.429461,
      "buy_sell_ratio_median": 1.44424,
      "txns_h1_median": 35.5
    },
    "rest": {
      "comparable_n": 21521,
      "liquidity_usd_median": 0.0,
      "volume_h1_median": 1443.84,
      "turnover_h1_median": 5.374962,
      "buy_sell_ratio_median": 1.25,
      "txns_h1_median": 30.0
    },
    "measured_to_rest_ratios": {
      "liquidity_median_ratio_measured_to_rest": null,
      "volume_median_ratio_measured_to_rest": 1.796186,
      "turnover_median_ratio_measured_to_rest": 0.0799,
      "buy_sell_ratio_median_ratio_measured_to_rest": 1.155392,
      "txns_median_ratio_measured_to_rest": 1.183333
    }
  },
  "interpretation_guard": "Market medians use only each token earliest stored historical observation. Missing-history tokens remain in coverage diagnostics.",
  "status": "ANALYZABLE"
}
