# Wallet500 — Measurable vs Rest Experiment

{
  "generated_at": "2026-09-02T02:05:41.352119+00:00",
  "method": "MEASURABLE_VS_REST_BIAS_EXPERIMENT_V1",
  "production_change": false,
  "truth_rule": "Do not interpret measurability as alpha until technical/data-coverage bias is separated from market-feature differences.",
  "tracked_total": 30952,
  "measured_now_n": 435,
  "rest_n": 30517,
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
        "bsc": 119,
        "solana": 207,
        "ethereum": 109
      },
      "measurement_statuses": {
        "VERIFIED_EXACT_PAIR": 435
      }
    },
    "rest": {
      "n": 30517,
      "pair_locked_n": 28693,
      "pair_locked_pct": 94.02,
      "earliest_snapshot_available_n": 20196,
      "earliest_snapshot_available_pct": 66.18,
      "current_pair_available_n": 20197,
      "current_pair_available_pct": 66.18,
      "chains": {
        "bsc": 11089,
        "ethereum": 1006,
        "solana": 18422
      },
      "measurement_statuses": {
        "AWAITING_EXACT_PAIR_OBSERVATION": 28695,
        "UNKNOWN": 69,
        "LEGACY_UNVERIFIABLE_PAIR": 1753
      }
    },
    "snapshot_coverage_gap_pp": 33.82
  },
  "market_layer_earliest_snapshot_only": {
    "measured": {
      "comparable_n": 435,
      "liquidity_usd_median": 0.1,
      "volume_h1_median": 2251.83,
      "turnover_h1_median": 0.356015,
      "buy_sell_ratio_median": 1.3,
      "txns_h1_median": 30.0
    },
    "rest": {
      "comparable_n": 20196,
      "liquidity_usd_median": 0.0,
      "volume_h1_median": 1414.905,
      "turnover_h1_median": 5.151508,
      "buy_sell_ratio_median": 1.25,
      "txns_h1_median": 30.0
    },
    "measured_to_rest_ratios": {
      "liquidity_median_ratio_measured_to_rest": null,
      "volume_median_ratio_measured_to_rest": 1.591506,
      "turnover_median_ratio_measured_to_rest": 0.069109,
      "buy_sell_ratio_median_ratio_measured_to_rest": 1.04,
      "txns_median_ratio_measured_to_rest": 1.0
    }
  },
  "interpretation_guard": "Market medians use only each token earliest stored historical observation. Missing-history tokens remain in coverage diagnostics.",
  "status": "ANALYZABLE"
}
