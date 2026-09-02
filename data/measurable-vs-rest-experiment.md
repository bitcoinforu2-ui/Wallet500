# Wallet500 — Measurable vs Rest Experiment

{
  "generated_at": "2026-09-02T09:57:42.673786+00:00",
  "method": "MEASURABLE_VS_REST_BIAS_EXPERIMENT_V1",
  "production_change": false,
  "truth_rule": "Do not interpret measurability as alpha until technical/data-coverage bias is separated from market-feature differences.",
  "tracked_total": 32993,
  "measured_now_n": 319,
  "rest_n": 32674,
  "technical_layer": {
    "measured": {
      "n": 319,
      "pair_locked_n": 319,
      "pair_locked_pct": 100.0,
      "earliest_snapshot_available_n": 319,
      "earliest_snapshot_available_pct": 100.0,
      "current_pair_available_n": 319,
      "current_pair_available_pct": 100.0,
      "chains": {
        "bsc": 112,
        "ethereum": 89,
        "solana": 118
      },
      "measurement_statuses": {
        "VERIFIED_EXACT_PAIR": 319
      }
    },
    "rest": {
      "n": 32674,
      "pair_locked_n": 30850,
      "pair_locked_pct": 94.42,
      "earliest_snapshot_available_n": 22355,
      "earliest_snapshot_available_pct": 68.42,
      "current_pair_available_n": 22356,
      "current_pair_available_pct": 68.42,
      "chains": {
        "bsc": 11877,
        "ethereum": 1075,
        "solana": 19722
      },
      "measurement_statuses": {
        "AWAITING_EXACT_PAIR_OBSERVATION": 30736,
        "UNKNOWN": 69,
        "LEGACY_UNVERIFIABLE_PAIR": 1753,
        "QUARANTINED_NON_EXECUTABLE_PRICE": 116
      }
    },
    "snapshot_coverage_gap_pp": 31.58
  },
  "market_layer_earliest_snapshot_only": {
    "measured": {
      "comparable_n": 319,
      "liquidity_usd_median": 2913.9,
      "volume_h1_median": 2360.41,
      "turnover_h1_median": 0.246918,
      "buy_sell_ratio_median": 1.5,
      "txns_h1_median": 30.0
    },
    "rest": {
      "comparable_n": 22355,
      "liquidity_usd_median": 0.0,
      "volume_h1_median": 1459.78,
      "turnover_h1_median": 5.676492,
      "buy_sell_ratio_median": 1.25,
      "txns_h1_median": 30.0
    },
    "measured_to_rest_ratios": {
      "liquidity_median_ratio_measured_to_rest": null,
      "volume_median_ratio_measured_to_rest": 1.616963,
      "turnover_median_ratio_measured_to_rest": 0.043498,
      "buy_sell_ratio_median_ratio_measured_to_rest": 1.2,
      "txns_median_ratio_measured_to_rest": 1.0
    }
  },
  "interpretation_guard": "Market medians use only each token earliest stored historical observation. Missing-history tokens remain in coverage diagnostics.",
  "status": "ANALYZABLE"
}
