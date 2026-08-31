# Wallet500 — Measurable vs Rest Experiment

{
  "generated_at": "2026-08-31T11:38:00.891805+00:00",
  "method": "MEASURABLE_VS_REST_BIAS_EXPERIMENT_V1",
  "production_change": false,
  "truth_rule": "Do not interpret measurability as alpha until technical/data-coverage bias is separated from market-feature differences.",
  "tracked_total": 20121,
  "measured_now_n": 479,
  "rest_n": 19642,
  "technical_layer": {
    "measured": {
      "n": 479,
      "pair_locked_n": 479,
      "pair_locked_pct": 100.0,
      "earliest_snapshot_available_n": 479,
      "earliest_snapshot_available_pct": 100.0,
      "current_pair_available_n": 479,
      "current_pair_available_pct": 100.0,
      "chains": {
        "ethereum": 115,
        "solana": 207,
        "bsc": 157
      },
      "measurement_statuses": {
        "VERIFIED_EXACT_PAIR": 479
      }
    },
    "rest": {
      "n": 19642,
      "pair_locked_n": 17812,
      "pair_locked_pct": 90.68,
      "earliest_snapshot_available_n": 9292,
      "earliest_snapshot_available_pct": 47.31,
      "current_pair_available_n": 9293,
      "current_pair_available_pct": 47.31,
      "chains": {
        "bsc": 7404,
        "ethereum": 694,
        "solana": 11544
      },
      "measurement_statuses": {
        "AWAITING_EXACT_PAIR_OBSERVATION": 17814,
        "UNKNOWN": 69,
        "LEGACY_UNVERIFIABLE_PAIR": 1759
      }
    },
    "snapshot_coverage_gap_pp": 52.69
  },
  "market_layer_earliest_snapshot_only": {
    "measured": {
      "comparable_n": 479,
      "liquidity_usd_median": 0.06,
      "volume_h1_median": 1580.61,
      "turnover_h1_median": 0.388474,
      "buy_sell_ratio_median": 1.333333,
      "txns_h1_median": 29.0
    },
    "rest": {
      "comparable_n": 9292,
      "liquidity_usd_median": 0.0,
      "volume_h1_median": 1245.205,
      "turnover_h1_median": 3.550616,
      "buy_sell_ratio_median": 1.25,
      "txns_h1_median": 27.0
    },
    "measured_to_rest_ratios": {
      "liquidity_median_ratio_measured_to_rest": null,
      "volume_median_ratio_measured_to_rest": 1.269357,
      "turnover_median_ratio_measured_to_rest": 0.10941,
      "buy_sell_ratio_median_ratio_measured_to_rest": 1.066666,
      "txns_median_ratio_measured_to_rest": 1.074074
    }
  },
  "interpretation_guard": "Market medians use only each token earliest stored historical observation. Missing-history tokens remain in coverage diagnostics.",
  "status": "ANALYZABLE"
}
