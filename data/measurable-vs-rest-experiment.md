# Wallet500 — Measurable vs Rest Experiment

{
  "generated_at": "2026-08-31T04:19:58.212454+00:00",
  "method": "MEASURABLE_VS_REST_BIAS_EXPERIMENT_V1",
  "production_change": false,
  "truth_rule": "Do not interpret measurability as alpha until technical/data-coverage bias is separated from market-feature differences.",
  "tracked_total": 18206,
  "measured_now_n": 463,
  "rest_n": 17743,
  "technical_layer": {
    "measured": {
      "n": 463,
      "pair_locked_n": 463,
      "pair_locked_pct": 100.0,
      "earliest_snapshot_available_n": 463,
      "earliest_snapshot_available_pct": 100.0,
      "current_pair_available_n": 463,
      "current_pair_available_pct": 100.0,
      "chains": {
        "ethereum": 107,
        "solana": 206,
        "bsc": 150
      },
      "measurement_statuses": {
        "VERIFIED_EXACT_PAIR": 463
      }
    },
    "rest": {
      "n": 17743,
      "pair_locked_n": 15913,
      "pair_locked_pct": 89.69,
      "earliest_snapshot_available_n": 7385,
      "earliest_snapshot_available_pct": 41.62,
      "current_pair_available_n": 7386,
      "current_pair_available_pct": 41.63,
      "chains": {
        "bsc": 6696,
        "ethereum": 665,
        "solana": 10382
      },
      "measurement_statuses": {
        "AWAITING_EXACT_PAIR_OBSERVATION": 15915,
        "UNKNOWN": 69,
        "LEGACY_UNVERIFIABLE_PAIR": 1759
      }
    },
    "snapshot_coverage_gap_pp": 58.38
  },
  "market_layer_earliest_snapshot_only": {
    "measured": {
      "comparable_n": 463,
      "liquidity_usd_median": 0.1,
      "volume_h1_median": 1582.77,
      "turnover_h1_median": 0.34354,
      "buy_sell_ratio_median": 1.315315,
      "txns_h1_median": 25.0
    },
    "rest": {
      "comparable_n": 7385,
      "liquidity_usd_median": 0.0,
      "volume_h1_median": 1151.33,
      "turnover_h1_median": 2.807014,
      "buy_sell_ratio_median": 1.243243,
      "txns_h1_median": 25.0
    },
    "measured_to_rest_ratios": {
      "liquidity_median_ratio_measured_to_rest": null,
      "volume_median_ratio_measured_to_rest": 1.374732,
      "turnover_median_ratio_measured_to_rest": 0.122386,
      "buy_sell_ratio_median_ratio_measured_to_rest": 1.057971,
      "txns_median_ratio_measured_to_rest": 1.0
    }
  },
  "interpretation_guard": "Market medians use only each token earliest stored historical observation. Missing-history tokens remain in coverage diagnostics.",
  "status": "ANALYZABLE"
}
