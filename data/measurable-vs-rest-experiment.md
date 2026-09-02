# Wallet500 — Measurable vs Rest Experiment

{
  "generated_at": "2026-09-02T06:08:57.651068+00:00",
  "method": "MEASURABLE_VS_REST_BIAS_EXPERIMENT_V1",
  "production_change": false,
  "truth_rule": "Do not interpret measurability as alpha until technical/data-coverage bias is separated from market-feature differences.",
  "tracked_total": 31876,
  "measured_now_n": 326,
  "rest_n": 31550,
  "technical_layer": {
    "measured": {
      "n": 326,
      "pair_locked_n": 326,
      "pair_locked_pct": 100.0,
      "earliest_snapshot_available_n": 326,
      "earliest_snapshot_available_pct": 100.0,
      "current_pair_available_n": 326,
      "current_pair_available_pct": 100.0,
      "chains": {
        "bsc": 94,
        "solana": 144,
        "ethereum": 88
      },
      "measurement_statuses": {
        "VERIFIED_EXACT_PAIR": 326
      }
    },
    "rest": {
      "n": 31550,
      "pair_locked_n": 29726,
      "pair_locked_pct": 94.22,
      "earliest_snapshot_available_n": 21230,
      "earliest_snapshot_available_pct": 67.29,
      "current_pair_available_n": 21231,
      "current_pair_available_pct": 67.29,
      "chains": {
        "bsc": 11482,
        "ethereum": 1053,
        "solana": 19015
      },
      "measurement_statuses": {
        "AWAITING_EXACT_PAIR_OBSERVATION": 29608,
        "UNKNOWN": 69,
        "LEGACY_UNVERIFIABLE_PAIR": 1753,
        "QUARANTINED_NON_EXECUTABLE_PRICE": 120
      }
    },
    "snapshot_coverage_gap_pp": 32.71
  },
  "market_layer_earliest_snapshot_only": {
    "measured": {
      "comparable_n": 326,
      "liquidity_usd_median": 812.375,
      "volume_h1_median": 2828.76,
      "turnover_h1_median": 0.761872,
      "buy_sell_ratio_median": 1.409091,
      "txns_h1_median": 39.0
    },
    "rest": {
      "comparable_n": 21230,
      "liquidity_usd_median": 0.0,
      "volume_h1_median": 1444.915,
      "turnover_h1_median": 5.331578,
      "buy_sell_ratio_median": 1.25,
      "txns_h1_median": 30.0
    },
    "measured_to_rest_ratios": {
      "liquidity_median_ratio_measured_to_rest": null,
      "volume_median_ratio_measured_to_rest": 1.957735,
      "turnover_median_ratio_measured_to_rest": 0.142898,
      "buy_sell_ratio_median_ratio_measured_to_rest": 1.127273,
      "txns_median_ratio_measured_to_rest": 1.3
    }
  },
  "interpretation_guard": "Market medians use only each token earliest stored historical observation. Missing-history tokens remain in coverage diagnostics.",
  "status": "ANALYZABLE"
}
