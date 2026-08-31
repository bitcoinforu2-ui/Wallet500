# Wallet500 — Measurable vs Rest Experiment

{
  "generated_at": "2026-08-31T05:49:40.578401+00:00",
  "method": "MEASURABLE_VS_REST_BIAS_EXPERIMENT_V1",
  "production_change": false,
  "truth_rule": "Do not interpret measurability as alpha until technical/data-coverage bias is separated from market-feature differences.",
  "tracked_total": 18617,
  "measured_now_n": 487,
  "rest_n": 18130,
  "technical_layer": {
    "measured": {
      "n": 487,
      "pair_locked_n": 487,
      "pair_locked_pct": 100.0,
      "earliest_snapshot_available_n": 487,
      "earliest_snapshot_available_pct": 100.0,
      "current_pair_available_n": 487,
      "current_pair_available_pct": 100.0,
      "chains": {
        "bsc": 165,
        "ethereum": 115,
        "solana": 207
      },
      "measurement_statuses": {
        "VERIFIED_EXACT_PAIR": 487
      }
    },
    "rest": {
      "n": 18130,
      "pair_locked_n": 16300,
      "pair_locked_pct": 89.91,
      "earliest_snapshot_available_n": 7774,
      "earliest_snapshot_available_pct": 42.88,
      "current_pair_available_n": 7775,
      "current_pair_available_pct": 42.88,
      "chains": {
        "bsc": 6816,
        "ethereum": 661,
        "solana": 10653
      },
      "measurement_statuses": {
        "AWAITING_EXACT_PAIR_OBSERVATION": 16302,
        "UNKNOWN": 69,
        "LEGACY_UNVERIFIABLE_PAIR": 1759
      }
    },
    "snapshot_coverage_gap_pp": 57.12
  },
  "market_layer_earliest_snapshot_only": {
    "measured": {
      "comparable_n": 487,
      "liquidity_usd_median": 0.09,
      "volume_h1_median": 1651.4,
      "turnover_h1_median": 0.315216,
      "buy_sell_ratio_median": 1.333333,
      "txns_h1_median": 27.0
    },
    "rest": {
      "comparable_n": 7774,
      "liquidity_usd_median": 0.0,
      "volume_h1_median": 1146.045,
      "turnover_h1_median": 2.807014,
      "buy_sell_ratio_median": 1.240696,
      "txns_h1_median": 25.0
    },
    "measured_to_rest_ratios": {
      "liquidity_median_ratio_measured_to_rest": null,
      "volume_median_ratio_measured_to_rest": 1.440956,
      "turnover_median_ratio_measured_to_rest": 0.112296,
      "buy_sell_ratio_median_ratio_measured_to_rest": 1.074665,
      "txns_median_ratio_measured_to_rest": 1.08
    }
  },
  "interpretation_guard": "Market medians use only each token earliest stored historical observation. Missing-history tokens remain in coverage diagnostics.",
  "status": "ANALYZABLE"
}
