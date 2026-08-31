# Wallet500 — Measurable vs Rest Experiment

{
  "generated_at": "2026-08-31T22:39:39.397016+00:00",
  "method": "MEASURABLE_VS_REST_BIAS_EXPERIMENT_V1",
  "production_change": false,
  "truth_rule": "Do not interpret measurability as alpha until technical/data-coverage bias is separated from market-feature differences.",
  "tracked_total": 23069,
  "measured_now_n": 422,
  "rest_n": 22647,
  "technical_layer": {
    "measured": {
      "n": 422,
      "pair_locked_n": 422,
      "pair_locked_pct": 100.0,
      "earliest_snapshot_available_n": 422,
      "earliest_snapshot_available_pct": 100.0,
      "current_pair_available_n": 422,
      "current_pair_available_pct": 100.0,
      "chains": {
        "bsc": 105,
        "solana": 207,
        "ethereum": 110
      },
      "measurement_statuses": {
        "VERIFIED_EXACT_PAIR": 422
      }
    },
    "rest": {
      "n": 22647,
      "pair_locked_n": 20818,
      "pair_locked_pct": 91.92,
      "earliest_snapshot_available_n": 12306,
      "earliest_snapshot_available_pct": 54.34,
      "current_pair_available_n": 12307,
      "current_pair_available_pct": 54.34,
      "chains": {
        "bsc": 8469,
        "ethereum": 800,
        "solana": 13378
      },
      "measurement_statuses": {
        "AWAITING_EXACT_PAIR_OBSERVATION": 20820,
        "UNKNOWN": 69,
        "LEGACY_UNVERIFIABLE_PAIR": 1758
      }
    },
    "snapshot_coverage_gap_pp": 45.66
  },
  "market_layer_earliest_snapshot_only": {
    "measured": {
      "comparable_n": 422,
      "liquidity_usd_median": 0.1,
      "volume_h1_median": 1380.66,
      "turnover_h1_median": 0.303017,
      "buy_sell_ratio_median": 1.396079,
      "txns_h1_median": 28.0
    },
    "rest": {
      "comparable_n": 12306,
      "liquidity_usd_median": 0.0,
      "volume_h1_median": 1350.375,
      "turnover_h1_median": 4.943034,
      "buy_sell_ratio_median": 1.23913,
      "txns_h1_median": 28.0
    },
    "measured_to_rest_ratios": {
      "liquidity_median_ratio_measured_to_rest": null,
      "volume_median_ratio_measured_to_rest": 1.022427,
      "turnover_median_ratio_measured_to_rest": 0.061302,
      "buy_sell_ratio_median_ratio_measured_to_rest": 1.126661,
      "txns_median_ratio_measured_to_rest": 1.0
    }
  },
  "interpretation_guard": "Market medians use only each token earliest stored historical observation. Missing-history tokens remain in coverage diagnostics.",
  "status": "ANALYZABLE"
}
