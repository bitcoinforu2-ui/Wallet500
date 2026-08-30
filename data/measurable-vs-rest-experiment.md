# Wallet500 — Measurable vs Rest Experiment

{
  "generated_at": "2026-08-30T21:40:48.139552+00:00",
  "method": "MEASURABLE_VS_REST_BIAS_EXPERIMENT_V1",
  "production_change": false,
  "truth_rule": "Do not interpret measurability as alpha until technical/data-coverage bias is separated from market-feature differences.",
  "tracked_total": 16513,
  "measured_now_n": 470,
  "rest_n": 16043,
  "technical_layer": {
    "measured": {
      "n": 470,
      "pair_locked_n": 470,
      "pair_locked_pct": 100.0,
      "earliest_snapshot_available_n": 470,
      "earliest_snapshot_available_pct": 100.0,
      "current_pair_available_n": 470,
      "current_pair_available_pct": 100.0,
      "chains": {
        "bsc": 153,
        "ethereum": 113,
        "solana": 204
      },
      "measurement_statuses": {
        "VERIFIED_EXACT_PAIR": 470
      }
    },
    "rest": {
      "n": 16043,
      "pair_locked_n": 14213,
      "pair_locked_pct": 88.59,
      "earliest_snapshot_available_n": 5676,
      "earliest_snapshot_available_pct": 35.38,
      "current_pair_available_n": 5677,
      "current_pair_available_pct": 35.39,
      "chains": {
        "bsc": 6066,
        "ethereum": 616,
        "solana": 9361
      },
      "measurement_statuses": {
        "AWAITING_EXACT_PAIR_OBSERVATION": 14215,
        "UNKNOWN": 69,
        "LEGACY_UNVERIFIABLE_PAIR": 1759
      }
    },
    "snapshot_coverage_gap_pp": 64.62
  },
  "market_layer_earliest_snapshot_only": {
    "measured": {
      "comparable_n": 470,
      "liquidity_usd_median": 0.05,
      "volume_h1_median": 1488.925,
      "turnover_h1_median": 0.506361,
      "buy_sell_ratio_median": 1.299573,
      "txns_h1_median": 25.0
    },
    "rest": {
      "comparable_n": 5676,
      "liquidity_usd_median": 0.0,
      "volume_h1_median": 1089.1,
      "turnover_h1_median": 1.721995,
      "buy_sell_ratio_median": 1.241854,
      "txns_h1_median": 24.0
    },
    "measured_to_rest_ratios": {
      "liquidity_median_ratio_measured_to_rest": null,
      "volume_median_ratio_measured_to_rest": 1.367115,
      "turnover_median_ratio_measured_to_rest": 0.294055,
      "buy_sell_ratio_median_ratio_measured_to_rest": 1.046478,
      "txns_median_ratio_measured_to_rest": 1.041667
    }
  },
  "interpretation_guard": "Market medians use only each token earliest stored historical observation. Missing-history tokens remain in coverage diagnostics.",
  "status": "ANALYZABLE"
}
