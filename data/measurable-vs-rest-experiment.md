# Wallet500 — Measurable vs Rest Experiment

{
  "generated_at": "2026-09-02T09:40:42.668118+00:00",
  "method": "MEASURABLE_VS_REST_BIAS_EXPERIMENT_V1",
  "production_change": false,
  "truth_rule": "Do not interpret measurability as alpha until technical/data-coverage bias is separated from market-feature differences.",
  "tracked_total": 32895,
  "measured_now_n": 313,
  "rest_n": 32582,
  "technical_layer": {
    "measured": {
      "n": 313,
      "pair_locked_n": 313,
      "pair_locked_pct": 100.0,
      "earliest_snapshot_available_n": 313,
      "earliest_snapshot_available_pct": 100.0,
      "current_pair_available_n": 313,
      "current_pair_available_pct": 100.0,
      "chains": {
        "bsc": 96,
        "solana": 140,
        "ethereum": 77
      },
      "measurement_statuses": {
        "VERIFIED_EXACT_PAIR": 313
      }
    },
    "rest": {
      "n": 32582,
      "pair_locked_n": 30758,
      "pair_locked_pct": 94.4,
      "earliest_snapshot_available_n": 22263,
      "earliest_snapshot_available_pct": 68.33,
      "current_pair_available_n": 22264,
      "current_pair_available_pct": 68.33,
      "chains": {
        "bsc": 11863,
        "ethereum": 1087,
        "solana": 19632
      },
      "measurement_statuses": {
        "AWAITING_EXACT_PAIR_OBSERVATION": 30637,
        "UNKNOWN": 69,
        "LEGACY_UNVERIFIABLE_PAIR": 1753,
        "QUARANTINED_NON_EXECUTABLE_PRICE": 123
      }
    },
    "snapshot_coverage_gap_pp": 31.67
  },
  "market_layer_earliest_snapshot_only": {
    "measured": {
      "comparable_n": 313,
      "liquidity_usd_median": 107.53,
      "volume_h1_median": 2509.39,
      "turnover_h1_median": 0.751504,
      "buy_sell_ratio_median": 1.547695,
      "txns_h1_median": 38.0
    },
    "rest": {
      "comparable_n": 22263,
      "liquidity_usd_median": 0.0,
      "volume_h1_median": 1462.91,
      "turnover_h1_median": 5.534164,
      "buy_sell_ratio_median": 1.25,
      "txns_h1_median": 30.0
    },
    "measured_to_rest_ratios": {
      "liquidity_median_ratio_measured_to_rest": null,
      "volume_median_ratio_measured_to_rest": 1.715341,
      "turnover_median_ratio_measured_to_rest": 0.135794,
      "buy_sell_ratio_median_ratio_measured_to_rest": 1.238156,
      "txns_median_ratio_measured_to_rest": 1.266667
    }
  },
  "interpretation_guard": "Market medians use only each token earliest stored historical observation. Missing-history tokens remain in coverage diagnostics.",
  "status": "ANALYZABLE"
}
