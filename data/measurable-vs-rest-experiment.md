# Wallet500 — Measurable vs Rest Experiment

{
  "generated_at": "2026-08-30T22:33:53.817657+00:00",
  "method": "MEASURABLE_VS_REST_BIAS_EXPERIMENT_V1",
  "production_change": false,
  "truth_rule": "Do not interpret measurability as alpha until technical/data-coverage bias is separated from market-feature differences.",
  "tracked_total": 16741,
  "measured_now_n": 461,
  "rest_n": 16280,
  "technical_layer": {
    "measured": {
      "n": 461,
      "pair_locked_n": 461,
      "pair_locked_pct": 100.0,
      "earliest_snapshot_available_n": 461,
      "earliest_snapshot_available_pct": 100.0,
      "current_pair_available_n": 461,
      "current_pair_available_pct": 100.0,
      "chains": {
        "bsc": 159,
        "ethereum": 97,
        "solana": 205
      },
      "measurement_statuses": {
        "VERIFIED_EXACT_PAIR": 461
      }
    },
    "rest": {
      "n": 16280,
      "pair_locked_n": 14450,
      "pair_locked_pct": 88.76,
      "earliest_snapshot_available_n": 5915,
      "earliest_snapshot_available_pct": 36.33,
      "current_pair_available_n": 5916,
      "current_pair_available_pct": 36.34,
      "chains": {
        "bsc": 6143,
        "ethereum": 637,
        "solana": 9500
      },
      "measurement_statuses": {
        "AWAITING_EXACT_PAIR_OBSERVATION": 14452,
        "UNKNOWN": 69,
        "LEGACY_UNVERIFIABLE_PAIR": 1759
      }
    },
    "snapshot_coverage_gap_pp": 63.67
  },
  "market_layer_earliest_snapshot_only": {
    "measured": {
      "comparable_n": 461,
      "liquidity_usd_median": 0.12,
      "volume_h1_median": 1613.95,
      "turnover_h1_median": 0.413139,
      "buy_sell_ratio_median": 1.317337,
      "txns_h1_median": 25.0
    },
    "rest": {
      "comparable_n": 5915,
      "liquidity_usd_median": 0.0,
      "volume_h1_median": 1093.72,
      "turnover_h1_median": 1.971958,
      "buy_sell_ratio_median": 1.241284,
      "txns_h1_median": 24.0
    },
    "measured_to_rest_ratios": {
      "liquidity_median_ratio_measured_to_rest": null,
      "volume_median_ratio_measured_to_rest": 1.475652,
      "turnover_median_ratio_measured_to_rest": 0.209507,
      "buy_sell_ratio_median_ratio_measured_to_rest": 1.06127,
      "txns_median_ratio_measured_to_rest": 1.041667
    }
  },
  "interpretation_guard": "Market medians use only each token earliest stored historical observation. Missing-history tokens remain in coverage diagnostics.",
  "status": "ANALYZABLE"
}
