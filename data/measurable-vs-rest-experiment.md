# Wallet500 — Measurable vs Rest Experiment

{
  "generated_at": "2026-08-31T13:51:28.514411+00:00",
  "method": "MEASURABLE_VS_REST_BIAS_EXPERIMENT_V1",
  "production_change": false,
  "truth_rule": "Do not interpret measurability as alpha until technical/data-coverage bias is separated from market-feature differences.",
  "tracked_total": 20656,
  "measured_now_n": 482,
  "rest_n": 20174,
  "technical_layer": {
    "measured": {
      "n": 482,
      "pair_locked_n": 482,
      "pair_locked_pct": 100.0,
      "earliest_snapshot_available_n": 482,
      "earliest_snapshot_available_pct": 100.0,
      "current_pair_available_n": 482,
      "current_pair_available_pct": 100.0,
      "chains": {
        "ethereum": 113,
        "solana": 205,
        "bsc": 164
      },
      "measurement_statuses": {
        "VERIFIED_EXACT_PAIR": 482
      }
    },
    "rest": {
      "n": 20174,
      "pair_locked_n": 18344,
      "pair_locked_pct": 90.93,
      "earliest_snapshot_available_n": 9825,
      "earliest_snapshot_available_pct": 48.7,
      "current_pair_available_n": 9826,
      "current_pair_available_pct": 48.71,
      "chains": {
        "bsc": 7605,
        "ethereum": 706,
        "solana": 11863
      },
      "measurement_statuses": {
        "AWAITING_EXACT_PAIR_OBSERVATION": 18346,
        "UNKNOWN": 69,
        "LEGACY_UNVERIFIABLE_PAIR": 1759
      }
    },
    "snapshot_coverage_gap_pp": 51.3
  },
  "market_layer_earliest_snapshot_only": {
    "measured": {
      "comparable_n": 482,
      "liquidity_usd_median": 0.25,
      "volume_h1_median": 1789.8,
      "turnover_h1_median": 0.41667,
      "buy_sell_ratio_median": 1.339996,
      "txns_h1_median": 31.0
    },
    "rest": {
      "comparable_n": 9825,
      "liquidity_usd_median": 0.0,
      "volume_h1_median": 1264.67,
      "turnover_h1_median": 4.066886,
      "buy_sell_ratio_median": 1.25,
      "txns_h1_median": 27.0
    },
    "measured_to_rest_ratios": {
      "liquidity_median_ratio_measured_to_rest": null,
      "volume_median_ratio_measured_to_rest": 1.415231,
      "turnover_median_ratio_measured_to_rest": 0.102454,
      "buy_sell_ratio_median_ratio_measured_to_rest": 1.071997,
      "txns_median_ratio_measured_to_rest": 1.148148
    }
  },
  "interpretation_guard": "Market medians use only each token earliest stored historical observation. Missing-history tokens remain in coverage diagnostics.",
  "status": "ANALYZABLE"
}
