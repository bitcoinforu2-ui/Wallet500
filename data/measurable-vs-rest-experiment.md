# Wallet500 — Measurable vs Rest Experiment

{
  "generated_at": "2026-09-02T04:18:44.489884+00:00",
  "method": "MEASURABLE_VS_REST_BIAS_EXPERIMENT_V1",
  "production_change": false,
  "truth_rule": "Do not interpret measurability as alpha until technical/data-coverage bias is separated from market-feature differences.",
  "tracked_total": 31523,
  "measured_now_n": 320,
  "rest_n": 31203,
  "technical_layer": {
    "measured": {
      "n": 320,
      "pair_locked_n": 320,
      "pair_locked_pct": 100.0,
      "earliest_snapshot_available_n": 320,
      "earliest_snapshot_available_pct": 100.0,
      "current_pair_available_n": 320,
      "current_pair_available_pct": 100.0,
      "chains": {
        "bsc": 97,
        "solana": 144,
        "ethereum": 79
      },
      "measurement_statuses": {
        "VERIFIED_EXACT_PAIR": 320
      }
    },
    "rest": {
      "n": 31203,
      "pair_locked_n": 29379,
      "pair_locked_pct": 94.15,
      "earliest_snapshot_available_n": 20883,
      "earliest_snapshot_available_pct": 66.93,
      "current_pair_available_n": 20884,
      "current_pair_available_pct": 66.93,
      "chains": {
        "bsc": 11298,
        "ethereum": 1046,
        "solana": 18859
      },
      "measurement_statuses": {
        "AWAITING_EXACT_PAIR_OBSERVATION": 29266,
        "UNKNOWN": 69,
        "LEGACY_UNVERIFIABLE_PAIR": 1753,
        "QUARANTINED_NON_EXECUTABLE_PRICE": 115
      }
    },
    "snapshot_coverage_gap_pp": 33.07
  },
  "market_layer_earliest_snapshot_only": {
    "measured": {
      "comparable_n": 320,
      "liquidity_usd_median": 3361.73,
      "volume_h1_median": 3267.095,
      "turnover_h1_median": 0.536698,
      "buy_sell_ratio_median": 1.423741,
      "txns_h1_median": 39.0
    },
    "rest": {
      "comparable_n": 20883,
      "liquidity_usd_median": 0.0,
      "volume_h1_median": 1420.74,
      "turnover_h1_median": 5.108059,
      "buy_sell_ratio_median": 1.25,
      "txns_h1_median": 30.0
    },
    "measured_to_rest_ratios": {
      "liquidity_median_ratio_measured_to_rest": null,
      "volume_median_ratio_measured_to_rest": 2.299573,
      "turnover_median_ratio_measured_to_rest": 0.105069,
      "buy_sell_ratio_median_ratio_measured_to_rest": 1.138993,
      "txns_median_ratio_measured_to_rest": 1.3
    }
  },
  "interpretation_guard": "Market medians use only each token earliest stored historical observation. Missing-history tokens remain in coverage diagnostics.",
  "status": "ANALYZABLE"
}
