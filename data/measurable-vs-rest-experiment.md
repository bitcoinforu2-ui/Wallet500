# Wallet500 — Measurable vs Rest Experiment

{
  "generated_at": "2026-09-02T04:14:40.222475+00:00",
  "method": "MEASURABLE_VS_REST_BIAS_EXPERIMENT_V1",
  "production_change": false,
  "truth_rule": "Do not interpret measurability as alpha until technical/data-coverage bias is separated from market-feature differences.",
  "tracked_total": 31523,
  "measured_now_n": 435,
  "rest_n": 31088,
  "technical_layer": {
    "measured": {
      "n": 435,
      "pair_locked_n": 435,
      "pair_locked_pct": 100.0,
      "earliest_snapshot_available_n": 435,
      "earliest_snapshot_available_pct": 100.0,
      "current_pair_available_n": 435,
      "current_pair_available_pct": 100.0,
      "chains": {
        "bsc": 117,
        "solana": 207,
        "ethereum": 111
      },
      "measurement_statuses": {
        "VERIFIED_EXACT_PAIR": 435
      }
    },
    "rest": {
      "n": 31088,
      "pair_locked_n": 29264,
      "pair_locked_pct": 94.13,
      "earliest_snapshot_available_n": 20768,
      "earliest_snapshot_available_pct": 66.8,
      "current_pair_available_n": 20769,
      "current_pair_available_pct": 66.81,
      "chains": {
        "bsc": 11278,
        "ethereum": 1014,
        "solana": 18796
      },
      "measurement_statuses": {
        "AWAITING_EXACT_PAIR_OBSERVATION": 29266,
        "UNKNOWN": 69,
        "LEGACY_UNVERIFIABLE_PAIR": 1753
      }
    },
    "snapshot_coverage_gap_pp": 33.2
  },
  "market_layer_earliest_snapshot_only": {
    "measured": {
      "comparable_n": 435,
      "liquidity_usd_median": 0.18,
      "volume_h1_median": 1745.46,
      "turnover_h1_median": 0.425198,
      "buy_sell_ratio_median": 1.363636,
      "txns_h1_median": 28.0
    },
    "rest": {
      "comparable_n": 20768,
      "liquidity_usd_median": 0.0,
      "volume_h1_median": 1427.495,
      "turnover_h1_median": 5.140268,
      "buy_sell_ratio_median": 1.25,
      "txns_h1_median": 30.0
    },
    "measured_to_rest_ratios": {
      "liquidity_median_ratio_measured_to_rest": null,
      "volume_median_ratio_measured_to_rest": 1.222743,
      "turnover_median_ratio_measured_to_rest": 0.082719,
      "buy_sell_ratio_median_ratio_measured_to_rest": 1.090909,
      "txns_median_ratio_measured_to_rest": 0.933333
    }
  },
  "interpretation_guard": "Market medians use only each token earliest stored historical observation. Missing-history tokens remain in coverage diagnostics.",
  "status": "ANALYZABLE"
}
