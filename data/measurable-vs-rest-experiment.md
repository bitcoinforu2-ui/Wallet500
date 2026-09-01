# Wallet500 — Measurable vs Rest Experiment

{
  "generated_at": "2026-09-01T09:10:36.136431+00:00",
  "method": "MEASURABLE_VS_REST_BIAS_EXPERIMENT_V1",
  "production_change": false,
  "truth_rule": "Do not interpret measurability as alpha until technical/data-coverage bias is separated from market-feature differences.",
  "tracked_total": 26267,
  "measured_now_n": 457,
  "rest_n": 25810,
  "technical_layer": {
    "measured": {
      "n": 457,
      "pair_locked_n": 457,
      "pair_locked_pct": 100.0,
      "earliest_snapshot_available_n": 457,
      "earliest_snapshot_available_pct": 100.0,
      "current_pair_available_n": 457,
      "current_pair_available_pct": 100.0,
      "chains": {
        "bsc": 142,
        "ethereum": 113,
        "solana": 202
      },
      "measurement_statuses": {
        "VERIFIED_EXACT_PAIR": 457
      }
    },
    "rest": {
      "n": 25810,
      "pair_locked_n": 23985,
      "pair_locked_pct": 92.93,
      "earliest_snapshot_available_n": 15479,
      "earliest_snapshot_available_pct": 59.97,
      "current_pair_available_n": 15480,
      "current_pair_available_pct": 59.98,
      "chains": {
        "bsc": 9438,
        "ethereum": 865,
        "solana": 15507
      },
      "measurement_statuses": {
        "AWAITING_EXACT_PAIR_OBSERVATION": 23987,
        "UNKNOWN": 69,
        "LEGACY_UNVERIFIABLE_PAIR": 1754
      }
    },
    "snapshot_coverage_gap_pp": 40.03
  },
  "market_layer_earliest_snapshot_only": {
    "measured": {
      "comparable_n": 457,
      "liquidity_usd_median": 0.77,
      "volume_h1_median": 1796.55,
      "turnover_h1_median": 0.281151,
      "buy_sell_ratio_median": 1.384615,
      "txns_h1_median": 27.0
    },
    "rest": {
      "comparable_n": 15479,
      "liquidity_usd_median": 0.0,
      "volume_h1_median": 1276.79,
      "turnover_h1_median": 5.063267,
      "buy_sell_ratio_median": 1.245675,
      "txns_h1_median": 29.0
    },
    "measured_to_rest_ratios": {
      "liquidity_median_ratio_measured_to_rest": null,
      "volume_median_ratio_measured_to_rest": 1.407083,
      "turnover_median_ratio_measured_to_rest": 0.055528,
      "buy_sell_ratio_median_ratio_measured_to_rest": 1.111538,
      "txns_median_ratio_measured_to_rest": 0.931034
    }
  },
  "interpretation_guard": "Market medians use only each token earliest stored historical observation. Missing-history tokens remain in coverage diagnostics.",
  "status": "ANALYZABLE"
}
