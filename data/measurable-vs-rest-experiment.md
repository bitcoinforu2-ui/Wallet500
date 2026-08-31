# Wallet500 — Measurable vs Rest Experiment

{
  "generated_at": "2026-08-31T13:07:55.428606+00:00",
  "method": "MEASURABLE_VS_REST_BIAS_EXPERIMENT_V1",
  "production_change": false,
  "truth_rule": "Do not interpret measurability as alpha until technical/data-coverage bias is separated from market-feature differences.",
  "tracked_total": 20512,
  "measured_now_n": 467,
  "rest_n": 20045,
  "technical_layer": {
    "measured": {
      "n": 467,
      "pair_locked_n": 467,
      "pair_locked_pct": 100.0,
      "earliest_snapshot_available_n": 467,
      "earliest_snapshot_available_pct": 100.0,
      "current_pair_available_n": 467,
      "current_pair_available_pct": 100.0,
      "chains": {
        "ethereum": 113,
        "solana": 208,
        "bsc": 146
      },
      "measurement_statuses": {
        "VERIFIED_EXACT_PAIR": 467
      }
    },
    "rest": {
      "n": 20045,
      "pair_locked_n": 18215,
      "pair_locked_pct": 90.87,
      "earliest_snapshot_available_n": 9696,
      "earliest_snapshot_available_pct": 48.37,
      "current_pair_available_n": 9697,
      "current_pair_available_pct": 48.38,
      "chains": {
        "bsc": 7560,
        "ethereum": 701,
        "solana": 11784
      },
      "measurement_statuses": {
        "AWAITING_EXACT_PAIR_OBSERVATION": 18217,
        "UNKNOWN": 69,
        "LEGACY_UNVERIFIABLE_PAIR": 1759
      }
    },
    "snapshot_coverage_gap_pp": 51.63
  },
  "market_layer_earliest_snapshot_only": {
    "measured": {
      "comparable_n": 467,
      "liquidity_usd_median": 0.06,
      "volume_h1_median": 1844.03,
      "turnover_h1_median": 0.607576,
      "buy_sell_ratio_median": 1.317647,
      "txns_h1_median": 28.0
    },
    "rest": {
      "comparable_n": 9696,
      "liquidity_usd_median": 0.0,
      "volume_h1_median": 1244.115,
      "turnover_h1_median": 3.72138,
      "buy_sell_ratio_median": 1.25,
      "txns_h1_median": 27.0
    },
    "measured_to_rest_ratios": {
      "liquidity_median_ratio_measured_to_rest": null,
      "volume_median_ratio_measured_to_rest": 1.482202,
      "turnover_median_ratio_measured_to_rest": 0.163266,
      "buy_sell_ratio_median_ratio_measured_to_rest": 1.054118,
      "txns_median_ratio_measured_to_rest": 1.037037
    }
  },
  "interpretation_guard": "Market medians use only each token earliest stored historical observation. Missing-history tokens remain in coverage diagnostics.",
  "status": "ANALYZABLE"
}
