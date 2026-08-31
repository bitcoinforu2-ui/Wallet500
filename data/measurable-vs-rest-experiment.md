# Wallet500 — Measurable vs Rest Experiment

{
  "generated_at": "2026-08-31T08:36:28.682892+00:00",
  "method": "MEASURABLE_VS_REST_BIAS_EXPERIMENT_V1",
  "production_change": false,
  "truth_rule": "Do not interpret measurability as alpha until technical/data-coverage bias is separated from market-feature differences.",
  "tracked_total": 19324,
  "measured_now_n": 413,
  "rest_n": 18911,
  "technical_layer": {
    "measured": {
      "n": 413,
      "pair_locked_n": 413,
      "pair_locked_pct": 100.0,
      "earliest_snapshot_available_n": 413,
      "earliest_snapshot_available_pct": 100.0,
      "current_pair_available_n": 413,
      "current_pair_available_pct": 100.0,
      "chains": {
        "bsc": 89,
        "ethereum": 113,
        "solana": 211
      },
      "measurement_statuses": {
        "VERIFIED_EXACT_PAIR": 413
      }
    },
    "rest": {
      "n": 18911,
      "pair_locked_n": 17081,
      "pair_locked_pct": 90.32,
      "earliest_snapshot_available_n": 8559,
      "earliest_snapshot_available_pct": 45.26,
      "current_pair_available_n": 8560,
      "current_pair_available_pct": 45.26,
      "chains": {
        "bsc": 7162,
        "ethereum": 678,
        "solana": 11071
      },
      "measurement_statuses": {
        "AWAITING_EXACT_PAIR_OBSERVATION": 17083,
        "UNKNOWN": 69,
        "LEGACY_UNVERIFIABLE_PAIR": 1759
      }
    },
    "snapshot_coverage_gap_pp": 54.74
  },
  "market_layer_earliest_snapshot_only": {
    "measured": {
      "comparable_n": 413,
      "liquidity_usd_median": 0.02,
      "volume_h1_median": 1314.25,
      "turnover_h1_median": 0.329733,
      "buy_sell_ratio_median": 1.304968,
      "txns_h1_median": 25.0
    },
    "rest": {
      "comparable_n": 8559,
      "liquidity_usd_median": 0.0,
      "volume_h1_median": 1226.01,
      "turnover_h1_median": 3.296821,
      "buy_sell_ratio_median": 1.25,
      "txns_h1_median": 26.0
    },
    "measured_to_rest_ratios": {
      "liquidity_median_ratio_measured_to_rest": null,
      "volume_median_ratio_measured_to_rest": 1.071973,
      "turnover_median_ratio_measured_to_rest": 0.100015,
      "buy_sell_ratio_median_ratio_measured_to_rest": 1.043974,
      "txns_median_ratio_measured_to_rest": 0.961538
    }
  },
  "interpretation_guard": "Market medians use only each token earliest stored historical observation. Missing-history tokens remain in coverage diagnostics.",
  "status": "ANALYZABLE"
}
