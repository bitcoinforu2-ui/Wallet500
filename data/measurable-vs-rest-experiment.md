# Wallet500 — Measurable vs Rest Experiment

{
  "generated_at": "2026-08-30T21:21:56.010341+00:00",
  "method": "MEASURABLE_VS_REST_BIAS_EXPERIMENT_V1",
  "production_change": false,
  "truth_rule": "Do not interpret measurability as alpha until technical/data-coverage bias is separated from market-feature differences.",
  "tracked_total": 16405,
  "measured_now_n": 474,
  "rest_n": 15931,
  "technical_layer": {
    "measured": {
      "n": 474,
      "pair_locked_n": 474,
      "pair_locked_pct": 100.0,
      "earliest_snapshot_available_n": 474,
      "earliest_snapshot_available_pct": 100.0,
      "current_pair_available_n": 474,
      "current_pair_available_pct": 100.0,
      "chains": {
        "bsc": 157,
        "ethereum": 113,
        "solana": 204
      },
      "measurement_statuses": {
        "VERIFIED_EXACT_PAIR": 474
      }
    },
    "rest": {
      "n": 15931,
      "pair_locked_n": 14101,
      "pair_locked_pct": 88.51,
      "earliest_snapshot_available_n": 5564,
      "earliest_snapshot_available_pct": 34.93,
      "current_pair_available_n": 5565,
      "current_pair_available_pct": 34.93,
      "chains": {
        "bsc": 6028,
        "ethereum": 613,
        "solana": 9290
      },
      "measurement_statuses": {
        "AWAITING_EXACT_PAIR_OBSERVATION": 14103,
        "UNKNOWN": 69,
        "LEGACY_UNVERIFIABLE_PAIR": 1759
      }
    },
    "snapshot_coverage_gap_pp": 65.07
  },
  "market_layer_earliest_snapshot_only": {
    "measured": {
      "comparable_n": 474,
      "liquidity_usd_median": 0.05,
      "volume_h1_median": 1242.33,
      "turnover_h1_median": 0.514639,
      "buy_sell_ratio_median": 1.316076,
      "txns_h1_median": 23.0
    },
    "rest": {
      "comparable_n": 5564,
      "liquidity_usd_median": 0.0,
      "volume_h1_median": 1135.855,
      "turnover_h1_median": 1.676365,
      "buy_sell_ratio_median": 1.24347,
      "txns_h1_median": 24.0
    },
    "measured_to_rest_ratios": {
      "liquidity_median_ratio_measured_to_rest": null,
      "volume_median_ratio_measured_to_rest": 1.09374,
      "turnover_median_ratio_measured_to_rest": 0.306997,
      "buy_sell_ratio_median_ratio_measured_to_rest": 1.05839,
      "txns_median_ratio_measured_to_rest": 0.958333
    }
  },
  "interpretation_guard": "Market medians use only each token earliest stored historical observation. Missing-history tokens remain in coverage diagnostics.",
  "status": "ANALYZABLE"
}
