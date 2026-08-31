# Wallet500 — Measurable vs Rest Experiment

{
  "generated_at": "2026-08-31T10:38:28.177046+00:00",
  "method": "MEASURABLE_VS_REST_BIAS_EXPERIMENT_V1",
  "production_change": false,
  "truth_rule": "Do not interpret measurability as alpha until technical/data-coverage bias is separated from market-feature differences.",
  "tracked_total": 19882,
  "measured_now_n": 454,
  "rest_n": 19428,
  "technical_layer": {
    "measured": {
      "n": 454,
      "pair_locked_n": 454,
      "pair_locked_pct": 100.0,
      "earliest_snapshot_available_n": 454,
      "earliest_snapshot_available_pct": 100.0,
      "current_pair_available_n": 454,
      "current_pair_available_pct": 100.0,
      "chains": {
        "ethereum": 115,
        "solana": 209,
        "bsc": 130
      },
      "measurement_statuses": {
        "VERIFIED_EXACT_PAIR": 454
      }
    },
    "rest": {
      "n": 19428,
      "pair_locked_n": 17598,
      "pair_locked_pct": 90.58,
      "earliest_snapshot_available_n": 9077,
      "earliest_snapshot_available_pct": 46.72,
      "current_pair_available_n": 9078,
      "current_pair_available_pct": 46.73,
      "chains": {
        "bsc": 7351,
        "ethereum": 690,
        "solana": 11387
      },
      "measurement_statuses": {
        "AWAITING_EXACT_PAIR_OBSERVATION": 17600,
        "UNKNOWN": 69,
        "LEGACY_UNVERIFIABLE_PAIR": 1759
      }
    },
    "snapshot_coverage_gap_pp": 53.28
  },
  "market_layer_earliest_snapshot_only": {
    "measured": {
      "comparable_n": 454,
      "liquidity_usd_median": 0.065,
      "volume_h1_median": 1382.095,
      "turnover_h1_median": 0.313146,
      "buy_sell_ratio_median": 1.286752,
      "txns_h1_median": 25.0
    },
    "rest": {
      "comparable_n": 9077,
      "liquidity_usd_median": 0.0,
      "volume_h1_median": 1245.88,
      "turnover_h1_median": 3.5,
      "buy_sell_ratio_median": 1.25,
      "txns_h1_median": 27.0
    },
    "measured_to_rest_ratios": {
      "liquidity_median_ratio_measured_to_rest": null,
      "volume_median_ratio_measured_to_rest": 1.109332,
      "turnover_median_ratio_measured_to_rest": 0.08947,
      "buy_sell_ratio_median_ratio_measured_to_rest": 1.029402,
      "txns_median_ratio_measured_to_rest": 0.925926
    }
  },
  "interpretation_guard": "Market medians use only each token earliest stored historical observation. Missing-history tokens remain in coverage diagnostics.",
  "status": "ANALYZABLE"
}
