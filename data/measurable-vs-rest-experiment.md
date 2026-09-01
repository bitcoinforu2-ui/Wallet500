# Wallet500 — Measurable vs Rest Experiment

{
  "generated_at": "2026-09-01T02:10:33.129095+00:00",
  "method": "MEASURABLE_VS_REST_BIAS_EXPERIMENT_V1",
  "production_change": false,
  "truth_rule": "Do not interpret measurability as alpha until technical/data-coverage bias is separated from market-feature differences.",
  "tracked_total": 23942,
  "measured_now_n": 429,
  "rest_n": 23513,
  "technical_layer": {
    "measured": {
      "n": 429,
      "pair_locked_n": 429,
      "pair_locked_pct": 100.0,
      "earliest_snapshot_available_n": 429,
      "earliest_snapshot_available_pct": 100.0,
      "current_pair_available_n": 429,
      "current_pair_available_pct": 100.0,
      "chains": {
        "bsc": 113,
        "ethereum": 112,
        "solana": 204
      },
      "measurement_statuses": {
        "VERIFIED_EXACT_PAIR": 429
      }
    },
    "rest": {
      "n": 23513,
      "pair_locked_n": 21686,
      "pair_locked_pct": 92.23,
      "earliest_snapshot_available_n": 13178,
      "earliest_snapshot_available_pct": 56.05,
      "current_pair_available_n": 13179,
      "current_pair_available_pct": 56.05,
      "chains": {
        "bsc": 8763,
        "ethereum": 827,
        "solana": 13923
      },
      "measurement_statuses": {
        "AWAITING_EXACT_PAIR_OBSERVATION": 21688,
        "UNKNOWN": 69,
        "LEGACY_UNVERIFIABLE_PAIR": 1756
      }
    },
    "snapshot_coverage_gap_pp": 43.95
  },
  "market_layer_earliest_snapshot_only": {
    "measured": {
      "comparable_n": 429,
      "liquidity_usd_median": 1.58,
      "volume_h1_median": 1651.4,
      "turnover_h1_median": 0.233335,
      "buy_sell_ratio_median": 1.313514,
      "txns_h1_median": 30.0
    },
    "rest": {
      "comparable_n": 13178,
      "liquidity_usd_median": 0.0,
      "volume_h1_median": 1347.885,
      "turnover_h1_median": 5.270399,
      "buy_sell_ratio_median": 1.245337,
      "txns_h1_median": 28.0
    },
    "measured_to_rest_ratios": {
      "liquidity_median_ratio_measured_to_rest": null,
      "volume_median_ratio_measured_to_rest": 1.225179,
      "turnover_median_ratio_measured_to_rest": 0.044273,
      "buy_sell_ratio_median_ratio_measured_to_rest": 1.054746,
      "txns_median_ratio_measured_to_rest": 1.071429
    }
  },
  "interpretation_guard": "Market medians use only each token earliest stored historical observation. Missing-history tokens remain in coverage diagnostics.",
  "status": "ANALYZABLE"
}
