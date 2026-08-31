# Wallet500 — Measurable vs Rest Experiment

{
  "generated_at": "2026-08-31T23:05:33.795646+00:00",
  "method": "MEASURABLE_VS_REST_BIAS_EXPERIMENT_V1",
  "production_change": false,
  "truth_rule": "Do not interpret measurability as alpha until technical/data-coverage bias is separated from market-feature differences.",
  "tracked_total": 23199,
  "measured_now_n": 409,
  "rest_n": 22790,
  "technical_layer": {
    "measured": {
      "n": 409,
      "pair_locked_n": 409,
      "pair_locked_pct": 100.0,
      "earliest_snapshot_available_n": 409,
      "earliest_snapshot_available_pct": 100.0,
      "current_pair_available_n": 409,
      "current_pair_available_pct": 100.0,
      "chains": {
        "bsc": 91,
        "solana": 208,
        "ethereum": 110
      },
      "measurement_statuses": {
        "VERIFIED_EXACT_PAIR": 409
      }
    },
    "rest": {
      "n": 22790,
      "pair_locked_n": 20962,
      "pair_locked_pct": 91.98,
      "earliest_snapshot_available_n": 12450,
      "earliest_snapshot_available_pct": 54.63,
      "current_pair_available_n": 12451,
      "current_pair_available_pct": 54.63,
      "chains": {
        "bsc": 8512,
        "ethereum": 804,
        "solana": 13474
      },
      "measurement_statuses": {
        "AWAITING_EXACT_PAIR_OBSERVATION": 20964,
        "UNKNOWN": 69,
        "LEGACY_UNVERIFIABLE_PAIR": 1757
      }
    },
    "snapshot_coverage_gap_pp": 45.37
  },
  "market_layer_earliest_snapshot_only": {
    "measured": {
      "comparable_n": 409,
      "liquidity_usd_median": 0.02,
      "volume_h1_median": 1099.7,
      "turnover_h1_median": 0.227339,
      "buy_sell_ratio_median": 1.292093,
      "txns_h1_median": 25.0
    },
    "rest": {
      "comparable_n": 12450,
      "liquidity_usd_median": 0.0,
      "volume_h1_median": 1357.255,
      "turnover_h1_median": 4.999358,
      "buy_sell_ratio_median": 1.243195,
      "txns_h1_median": 29.0
    },
    "measured_to_rest_ratios": {
      "liquidity_median_ratio_measured_to_rest": null,
      "volume_median_ratio_measured_to_rest": 0.810238,
      "turnover_median_ratio_measured_to_rest": 0.045474,
      "buy_sell_ratio_median_ratio_measured_to_rest": 1.039333,
      "txns_median_ratio_measured_to_rest": 0.862069
    }
  },
  "interpretation_guard": "Market medians use only each token earliest stored historical observation. Missing-history tokens remain in coverage diagnostics.",
  "status": "ANALYZABLE"
}
