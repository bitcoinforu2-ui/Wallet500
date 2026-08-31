# Wallet500 — Measurable vs Rest Experiment

{
  "generated_at": "2026-08-31T05:07:21.405390+00:00",
  "method": "MEASURABLE_VS_REST_BIAS_EXPERIMENT_V1",
  "production_change": false,
  "truth_rule": "Do not interpret measurability as alpha until technical/data-coverage bias is separated from market-feature differences.",
  "tracked_total": 18421,
  "measured_now_n": 460,
  "rest_n": 17961,
  "technical_layer": {
    "measured": {
      "n": 460,
      "pair_locked_n": 460,
      "pair_locked_pct": 100.0,
      "earliest_snapshot_available_n": 460,
      "earliest_snapshot_available_pct": 100.0,
      "current_pair_available_n": 460,
      "current_pair_available_pct": 100.0,
      "chains": {
        "bsc": 152,
        "ethereum": 103,
        "solana": 205
      },
      "measurement_statuses": {
        "VERIFIED_EXACT_PAIR": 460
      }
    },
    "rest": {
      "n": 17961,
      "pair_locked_n": 16131,
      "pair_locked_pct": 89.81,
      "earliest_snapshot_available_n": 7603,
      "earliest_snapshot_available_pct": 42.33,
      "current_pair_available_n": 7604,
      "current_pair_available_pct": 42.34,
      "chains": {
        "bsc": 6770,
        "ethereum": 670,
        "solana": 10521
      },
      "measurement_statuses": {
        "AWAITING_EXACT_PAIR_OBSERVATION": 16133,
        "UNKNOWN": 69,
        "LEGACY_UNVERIFIABLE_PAIR": 1759
      }
    },
    "snapshot_coverage_gap_pp": 57.67
  },
  "market_layer_earliest_snapshot_only": {
    "measured": {
      "comparable_n": 460,
      "liquidity_usd_median": 0.12,
      "volume_h1_median": 1592.965,
      "turnover_h1_median": 0.330755,
      "buy_sell_ratio_median": 1.333333,
      "txns_h1_median": 30.0
    },
    "rest": {
      "comparable_n": 7603,
      "liquidity_usd_median": 0.0,
      "volume_h1_median": 1151.33,
      "turnover_h1_median": 2.846891,
      "buy_sell_ratio_median": 1.241379,
      "txns_h1_median": 25.0
    },
    "measured_to_rest_ratios": {
      "liquidity_median_ratio_measured_to_rest": null,
      "volume_median_ratio_measured_to_rest": 1.383587,
      "turnover_median_ratio_measured_to_rest": 0.116181,
      "buy_sell_ratio_median_ratio_measured_to_rest": 1.074074,
      "txns_median_ratio_measured_to_rest": 1.2
    }
  },
  "interpretation_guard": "Market medians use only each token earliest stored historical observation. Missing-history tokens remain in coverage diagnostics.",
  "status": "ANALYZABLE"
}
