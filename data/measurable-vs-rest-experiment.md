# Wallet500 — Measurable vs Rest Experiment

{
  "generated_at": "2026-09-01T15:37:23.508020+00:00",
  "method": "MEASURABLE_VS_REST_BIAS_EXPERIMENT_V1",
  "production_change": false,
  "truth_rule": "Do not interpret measurability as alpha until technical/data-coverage bias is separated from market-feature differences.",
  "tracked_total": 28404,
  "measured_now_n": 478,
  "rest_n": 27926,
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
        "solana": 201,
        "bsc": 159,
        "ethereum": 118
      },
      "measurement_statuses": {
        "VERIFIED_EXACT_PAIR": 478
      }
    },
    "rest": {
      "n": 27926,
      "pair_locked_n": 26101,
      "pair_locked_pct": 93.46,
      "earliest_snapshot_available_n": 17600,
      "earliest_snapshot_available_pct": 63.02,
      "current_pair_available_n": 17601,
      "current_pair_available_pct": 63.03,
      "chains": {
        "bsc": 10107,
        "ethereum": 916,
        "solana": 16903
      },
      "measurement_statuses": {
        "AWAITING_EXACT_PAIR_OBSERVATION": 26103,
        "UNKNOWN": 69,
        "LEGACY_UNVERIFIABLE_PAIR": 1754
      }
    },
    "snapshot_coverage_gap_pp": 36.98
  },
  "market_layer_earliest_snapshot_only": {
    "measured": {
      "comparable_n": 478,
      "liquidity_usd_median": 0.12,
      "volume_h1_median": 1527.08,
      "turnover_h1_median": 0.342932,
      "buy_sell_ratio_median": 1.352254,
      "txns_h1_median": 24.0
    },
    "rest": {
      "comparable_n": 17600,
      "liquidity_usd_median": 0.0,
      "volume_h1_median": 1331.335,
      "turnover_h1_median": 4.805355,
      "buy_sell_ratio_median": 1.242424,
      "txns_h1_median": 29.0
    },
    "measured_to_rest_ratios": {
      "liquidity_median_ratio_measured_to_rest": null,
      "volume_median_ratio_measured_to_rest": 1.147029,
      "turnover_median_ratio_measured_to_rest": 0.071365,
      "buy_sell_ratio_median_ratio_measured_to_rest": 1.0884,
      "txns_median_ratio_measured_to_rest": 0.827586
    }
  },
  "interpretation_guard": "Market medians use only each token earliest stored historical observation. Missing-history tokens remain in coverage diagnostics.",
  "status": "ANALYZABLE"
}
