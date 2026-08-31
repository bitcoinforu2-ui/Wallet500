# Wallet500 — Measurable vs Rest Experiment

{
  "generated_at": "2026-08-31T00:06:32.842201+00:00",
  "method": "MEASURABLE_VS_REST_BIAS_EXPERIMENT_V1",
  "production_change": false,
  "truth_rule": "Do not interpret measurability as alpha until technical/data-coverage bias is separated from market-feature differences.",
  "tracked_total": 17137,
  "measured_now_n": 481,
  "rest_n": 16656,
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
        "bsc": 155,
        "ethereum": 116,
        "solana": 210
      },
      "measurement_statuses": {
        "VERIFIED_EXACT_PAIR": 481
      }
    },
    "rest": {
      "n": 16656,
      "pair_locked_n": 14826,
      "pair_locked_pct": 89.01,
      "earliest_snapshot_available_n": 6294,
      "earliest_snapshot_available_pct": 37.79,
      "current_pair_available_n": 6295,
      "current_pair_available_pct": 37.79,
      "chains": {
        "bsc": 6275,
        "ethereum": 627,
        "solana": 9754
      },
      "measurement_statuses": {
        "AWAITING_EXACT_PAIR_OBSERVATION": 14828,
        "UNKNOWN": 69,
        "LEGACY_UNVERIFIABLE_PAIR": 1759
      }
    },
    "snapshot_coverage_gap_pp": 62.21
  },
  "market_layer_earliest_snapshot_only": {
    "measured": {
      "comparable_n": 481,
      "liquidity_usd_median": 0.01,
      "volume_h1_median": 1484.87,
      "turnover_h1_median": 0.514639,
      "buy_sell_ratio_median": 1.311927,
      "txns_h1_median": 26.0
    },
    "rest": {
      "comparable_n": 6294,
      "liquidity_usd_median": 0.0,
      "volume_h1_median": 1140.445,
      "turnover_h1_median": 2.089145,
      "buy_sell_ratio_median": 1.244542,
      "txns_h1_median": 25.0
    },
    "measured_to_rest_ratios": {
      "liquidity_median_ratio_measured_to_rest": null,
      "volume_median_ratio_measured_to_rest": 1.302009,
      "turnover_median_ratio_measured_to_rest": 0.24634,
      "buy_sell_ratio_median_ratio_measured_to_rest": 1.054144,
      "txns_median_ratio_measured_to_rest": 1.04
    }
  },
  "interpretation_guard": "Market medians use only each token earliest stored historical observation. Missing-history tokens remain in coverage diagnostics.",
  "status": "ANALYZABLE"
}
