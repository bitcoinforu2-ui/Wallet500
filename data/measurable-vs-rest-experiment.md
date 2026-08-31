# Wallet500 — Measurable vs Rest Experiment

{
  "generated_at": "2026-08-31T05:23:13.143789+00:00",
  "method": "MEASURABLE_VS_REST_BIAS_EXPERIMENT_V1",
  "production_change": false,
  "truth_rule": "Do not interpret measurability as alpha until technical/data-coverage bias is separated from market-feature differences.",
  "tracked_total": 18497,
  "measured_now_n": 478,
  "rest_n": 18019,
  "technical_layer": {
    "measured": {
      "n": 478,
      "pair_locked_n": 478,
      "pair_locked_pct": 100.0,
      "earliest_snapshot_available_n": 478,
      "earliest_snapshot_available_pct": 100.0,
      "current_pair_available_n": 478,
      "current_pair_available_pct": 100.0,
      "chains": {
        "bsc": 160,
        "ethereum": 115,
        "solana": 203
      },
      "measurement_statuses": {
        "VERIFIED_EXACT_PAIR": 478
      }
    },
    "rest": {
      "n": 18019,
      "pair_locked_n": 16189,
      "pair_locked_pct": 89.84,
      "earliest_snapshot_available_n": 7663,
      "earliest_snapshot_available_pct": 42.53,
      "current_pair_available_n": 7664,
      "current_pair_available_pct": 42.53,
      "chains": {
        "bsc": 6780,
        "ethereum": 658,
        "solana": 10581
      },
      "measurement_statuses": {
        "AWAITING_EXACT_PAIR_OBSERVATION": 16191,
        "UNKNOWN": 69,
        "LEGACY_UNVERIFIABLE_PAIR": 1759
      }
    },
    "snapshot_coverage_gap_pp": 57.47
  },
  "market_layer_earliest_snapshot_only": {
    "measured": {
      "comparable_n": 478,
      "liquidity_usd_median": 1.55,
      "volume_h1_median": 1756.23,
      "turnover_h1_median": 0.298861,
      "buy_sell_ratio_median": 1.325798,
      "txns_h1_median": 29.0
    },
    "rest": {
      "comparable_n": 7663,
      "liquidity_usd_median": 0.0,
      "volume_h1_median": 1143.62,
      "turnover_h1_median": 2.92077,
      "buy_sell_ratio_median": 1.241284,
      "txns_h1_median": 25.0
    },
    "measured_to_rest_ratios": {
      "liquidity_median_ratio_measured_to_rest": null,
      "volume_median_ratio_measured_to_rest": 1.535676,
      "turnover_median_ratio_measured_to_rest": 0.102323,
      "buy_sell_ratio_median_ratio_measured_to_rest": 1.068086,
      "txns_median_ratio_measured_to_rest": 1.16
    }
  },
  "interpretation_guard": "Market medians use only each token earliest stored historical observation. Missing-history tokens remain in coverage diagnostics.",
  "status": "ANALYZABLE"
}
