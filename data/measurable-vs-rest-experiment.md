# Wallet500 — Measurable vs Rest Experiment

{
  "generated_at": "2026-09-01T14:49:43.376980+00:00",
  "method": "MEASURABLE_VS_REST_BIAS_EXPERIMENT_V1",
  "production_change": false,
  "truth_rule": "Do not interpret measurability as alpha until technical/data-coverage bias is separated from market-feature differences.",
  "tracked_total": 28133,
  "measured_now_n": 481,
  "rest_n": 27652,
  "technical_layer": {
    "measured": {
      "n": 481,
      "pair_locked_n": 481,
      "pair_locked_pct": 100.0,
      "earliest_snapshot_available_n": 481,
      "earliest_snapshot_available_pct": 100.0,
      "current_pair_available_n": 481,
      "current_pair_available_pct": 100.0,
      "chains": {
        "solana": 207,
        "bsc": 157,
        "ethereum": 117
      },
      "measurement_statuses": {
        "VERIFIED_EXACT_PAIR": 481
      }
    },
    "rest": {
      "n": 27652,
      "pair_locked_n": 25827,
      "pair_locked_pct": 93.4,
      "earliest_snapshot_available_n": 17326,
      "earliest_snapshot_available_pct": 62.66,
      "current_pair_available_n": 17327,
      "current_pair_available_pct": 62.66,
      "chains": {
        "bsc": 10007,
        "ethereum": 906,
        "solana": 16739
      },
      "measurement_statuses": {
        "AWAITING_EXACT_PAIR_OBSERVATION": 25829,
        "UNKNOWN": 69,
        "LEGACY_UNVERIFIABLE_PAIR": 1754
      }
    },
    "snapshot_coverage_gap_pp": 37.34
  },
  "market_layer_earliest_snapshot_only": {
    "measured": {
      "comparable_n": 481,
      "liquidity_usd_median": 1.57,
      "volume_h1_median": 1712.43,
      "turnover_h1_median": 0.375359,
      "buy_sell_ratio_median": 1.351852,
      "txns_h1_median": 28.0
    },
    "rest": {
      "comparable_n": 17326,
      "liquidity_usd_median": 0.0,
      "volume_h1_median": 1305.065,
      "turnover_h1_median": 4.85781,
      "buy_sell_ratio_median": 1.242857,
      "txns_h1_median": 29.0
    },
    "measured_to_rest_ratios": {
      "liquidity_median_ratio_measured_to_rest": null,
      "volume_median_ratio_measured_to_rest": 1.312142,
      "turnover_median_ratio_measured_to_rest": 0.077269,
      "buy_sell_ratio_median_ratio_measured_to_rest": 1.087697,
      "txns_median_ratio_measured_to_rest": 0.965517
    }
  },
  "interpretation_guard": "Market medians use only each token earliest stored historical observation. Missing-history tokens remain in coverage diagnostics.",
  "status": "ANALYZABLE"
}
