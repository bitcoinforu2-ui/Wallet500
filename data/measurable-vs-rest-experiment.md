# Wallet500 — Measurable vs Rest Experiment

{
  "generated_at": "2026-08-31T14:37:58.608484+00:00",
  "method": "MEASURABLE_VS_REST_BIAS_EXPERIMENT_V1",
  "production_change": false,
  "truth_rule": "Do not interpret measurability as alpha until technical/data-coverage bias is separated from market-feature differences.",
  "tracked_total": 20869,
  "measured_now_n": 451,
  "rest_n": 20418,
  "technical_layer": {
    "measured": {
      "n": 451,
      "pair_locked_n": 451,
      "pair_locked_pct": 100.0,
      "earliest_snapshot_available_n": 451,
      "earliest_snapshot_available_pct": 100.0,
      "current_pair_available_n": 451,
      "current_pair_available_pct": 100.0,
      "chains": {
        "ethereum": 113,
        "solana": 206,
        "bsc": 132
      },
      "measurement_statuses": {
        "VERIFIED_EXACT_PAIR": 451
      }
    },
    "rest": {
      "n": 20418,
      "pair_locked_n": 18588,
      "pair_locked_pct": 91.04,
      "earliest_snapshot_available_n": 10069,
      "earliest_snapshot_available_pct": 49.31,
      "current_pair_available_n": 10070,
      "current_pair_available_pct": 49.32,
      "chains": {
        "bsc": 7705,
        "ethereum": 708,
        "solana": 12005
      },
      "measurement_statuses": {
        "AWAITING_EXACT_PAIR_OBSERVATION": 18590,
        "UNKNOWN": 69,
        "LEGACY_UNVERIFIABLE_PAIR": 1759
      }
    },
    "snapshot_coverage_gap_pp": 50.69
  },
  "market_layer_earliest_snapshot_only": {
    "measured": {
      "comparable_n": 451,
      "liquidity_usd_median": 0.12,
      "volume_h1_median": 1837.42,
      "turnover_h1_median": 0.643433,
      "buy_sell_ratio_median": 1.362069,
      "txns_h1_median": 33.0
    },
    "rest": {
      "comparable_n": 10069,
      "liquidity_usd_median": 0.0,
      "volume_h1_median": 1276.79,
      "turnover_h1_median": 4.130671,
      "buy_sell_ratio_median": 1.25,
      "txns_h1_median": 27.0
    },
    "measured_to_rest_ratios": {
      "liquidity_median_ratio_measured_to_rest": null,
      "volume_median_ratio_measured_to_rest": 1.439093,
      "turnover_median_ratio_measured_to_rest": 0.15577,
      "buy_sell_ratio_median_ratio_measured_to_rest": 1.089655,
      "txns_median_ratio_measured_to_rest": 1.222222
    }
  },
  "interpretation_guard": "Market medians use only each token earliest stored historical observation. Missing-history tokens remain in coverage diagnostics.",
  "status": "ANALYZABLE"
}
