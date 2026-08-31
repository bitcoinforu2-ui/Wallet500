# Wallet500 — Measurable vs Rest Experiment

{
  "generated_at": "2026-08-31T17:36:20.816471+00:00",
  "method": "MEASURABLE_VS_REST_BIAS_EXPERIMENT_V1",
  "production_change": false,
  "truth_rule": "Do not interpret measurability as alpha until technical/data-coverage bias is separated from market-feature differences.",
  "tracked_total": 21698,
  "measured_now_n": 403,
  "rest_n": 21295,
  "technical_layer": {
    "measured": {
      "n": 403,
      "pair_locked_n": 403,
      "pair_locked_pct": 100.0,
      "earliest_snapshot_available_n": 403,
      "earliest_snapshot_available_pct": 100.0,
      "current_pair_available_n": 403,
      "current_pair_available_pct": 100.0,
      "chains": {
        "bsc": 84,
        "ethereum": 113,
        "solana": 206
      },
      "measurement_statuses": {
        "VERIFIED_EXACT_PAIR": 403
      }
    },
    "rest": {
      "n": 21295,
      "pair_locked_n": 19465,
      "pair_locked_pct": 91.41,
      "earliest_snapshot_available_n": 10948,
      "earliest_snapshot_available_pct": 51.41,
      "current_pair_available_n": 10949,
      "current_pair_available_pct": 51.42,
      "chains": {
        "bsc": 8063,
        "ethereum": 731,
        "solana": 12501
      },
      "measurement_statuses": {
        "AWAITING_EXACT_PAIR_OBSERVATION": 19467,
        "UNKNOWN": 69,
        "LEGACY_UNVERIFIABLE_PAIR": 1759
      }
    },
    "snapshot_coverage_gap_pp": 48.59
  },
  "market_layer_earliest_snapshot_only": {
    "measured": {
      "comparable_n": 403,
      "liquidity_usd_median": 0.14,
      "volume_h1_median": 1521.47,
      "turnover_h1_median": 0.392085,
      "buy_sell_ratio_median": 1.219608,
      "txns_h1_median": 29.0
    },
    "rest": {
      "comparable_n": 10948,
      "liquidity_usd_median": 0.0,
      "volume_h1_median": 1360.495,
      "turnover_h1_median": 4.924375,
      "buy_sell_ratio_median": 1.248119,
      "txns_h1_median": 28.0
    },
    "measured_to_rest_ratios": {
      "liquidity_median_ratio_measured_to_rest": null,
      "volume_median_ratio_measured_to_rest": 1.118321,
      "turnover_median_ratio_measured_to_rest": 0.079621,
      "buy_sell_ratio_median_ratio_measured_to_rest": 0.977157,
      "txns_median_ratio_measured_to_rest": 1.035714
    }
  },
  "interpretation_guard": "Market medians use only each token earliest stored historical observation. Missing-history tokens remain in coverage diagnostics.",
  "status": "ANALYZABLE"
}
