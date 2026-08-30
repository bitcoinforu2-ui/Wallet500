# Wallet500 — Measurable vs Rest Experiment

{
  "generated_at": "2026-08-30T23:10:24.420933+00:00",
  "method": "MEASURABLE_VS_REST_BIAS_EXPERIMENT_V1",
  "production_change": false,
  "truth_rule": "Do not interpret measurability as alpha until technical/data-coverage bias is separated from market-feature differences.",
  "tracked_total": 16866,
  "measured_now_n": 475,
  "rest_n": 16391,
  "technical_layer": {
    "measured": {
      "n": 475,
      "pair_locked_n": 475,
      "pair_locked_pct": 100.0,
      "earliest_snapshot_available_n": 475,
      "earliest_snapshot_available_pct": 100.0,
      "current_pair_available_n": 475,
      "current_pair_available_pct": 100.0,
      "chains": {
        "bsc": 154,
        "ethereum": 115,
        "solana": 206
      },
      "measurement_statuses": {
        "VERIFIED_EXACT_PAIR": 475
      }
    },
    "rest": {
      "n": 16391,
      "pair_locked_n": 14561,
      "pair_locked_pct": 88.84,
      "earliest_snapshot_available_n": 6027,
      "earliest_snapshot_available_pct": 36.77,
      "current_pair_available_n": 6028,
      "current_pair_available_pct": 36.78,
      "chains": {
        "bsc": 6197,
        "ethereum": 621,
        "solana": 9573
      },
      "measurement_statuses": {
        "AWAITING_EXACT_PAIR_OBSERVATION": 14563,
        "UNKNOWN": 69,
        "LEGACY_UNVERIFIABLE_PAIR": 1759
      }
    },
    "snapshot_coverage_gap_pp": 63.23
  },
  "market_layer_earliest_snapshot_only": {
    "measured": {
      "comparable_n": 475,
      "liquidity_usd_median": 0.08,
      "volume_h1_median": 1489.26,
      "turnover_h1_median": 0.465509,
      "buy_sell_ratio_median": 1.4375,
      "txns_h1_median": 25.0
    },
    "rest": {
      "comparable_n": 6027,
      "liquidity_usd_median": 0.0,
      "volume_h1_median": 1121.63,
      "turnover_h1_median": 2.0,
      "buy_sell_ratio_median": 1.240385,
      "txns_h1_median": 24.0
    },
    "measured_to_rest_ratios": {
      "liquidity_median_ratio_measured_to_rest": null,
      "volume_median_ratio_measured_to_rest": 1.327764,
      "turnover_median_ratio_measured_to_rest": 0.232755,
      "buy_sell_ratio_median_ratio_measured_to_rest": 1.158914,
      "txns_median_ratio_measured_to_rest": 1.041667
    }
  },
  "interpretation_guard": "Market medians use only each token earliest stored historical observation. Missing-history tokens remain in coverage diagnostics.",
  "status": "ANALYZABLE"
}
