# Wallet500 — Measurable vs Rest Experiment

{
  "generated_at": "2026-08-31T07:45:15.494796+00:00",
  "method": "MEASURABLE_VS_REST_BIAS_EXPERIMENT_V1",
  "production_change": false,
  "truth_rule": "Do not interpret measurability as alpha until technical/data-coverage bias is separated from market-feature differences.",
  "tracked_total": 19019,
  "measured_now_n": 447,
  "rest_n": 18572,
  "technical_layer": {
    "measured": {
      "n": 447,
      "pair_locked_n": 447,
      "pair_locked_pct": 100.0,
      "earliest_snapshot_available_n": 447,
      "earliest_snapshot_available_pct": 100.0,
      "current_pair_available_n": 447,
      "current_pair_available_pct": 100.0,
      "chains": {
        "bsc": 128,
        "ethereum": 114,
        "solana": 205
      },
      "measurement_statuses": {
        "VERIFIED_EXACT_PAIR": 447
      }
    },
    "rest": {
      "n": 18572,
      "pair_locked_n": 16742,
      "pair_locked_pct": 90.15,
      "earliest_snapshot_available_n": 8218,
      "earliest_snapshot_available_pct": 44.25,
      "current_pair_available_n": 8219,
      "current_pair_available_pct": 44.25,
      "chains": {
        "bsc": 7016,
        "ethereum": 663,
        "solana": 10893
      },
      "measurement_statuses": {
        "AWAITING_EXACT_PAIR_OBSERVATION": 16744,
        "UNKNOWN": 69,
        "LEGACY_UNVERIFIABLE_PAIR": 1759
      }
    },
    "snapshot_coverage_gap_pp": 55.75
  },
  "market_layer_earliest_snapshot_only": {
    "measured": {
      "comparable_n": 447,
      "liquidity_usd_median": 0.07,
      "volume_h1_median": 1992.45,
      "turnover_h1_median": 0.916667,
      "buy_sell_ratio_median": 1.333333,
      "txns_h1_median": 31.0
    },
    "rest": {
      "comparable_n": 8218,
      "liquidity_usd_median": 0.0,
      "volume_h1_median": 1178.05,
      "turnover_h1_median": 2.760111,
      "buy_sell_ratio_median": 1.25,
      "txns_h1_median": 26.0
    },
    "measured_to_rest_ratios": {
      "liquidity_median_ratio_measured_to_rest": null,
      "volume_median_ratio_measured_to_rest": 1.691312,
      "turnover_median_ratio_measured_to_rest": 0.332112,
      "buy_sell_ratio_median_ratio_measured_to_rest": 1.066666,
      "txns_median_ratio_measured_to_rest": 1.192308
    }
  },
  "interpretation_guard": "Market medians use only each token earliest stored historical observation. Missing-history tokens remain in coverage diagnostics.",
  "status": "ANALYZABLE"
}
