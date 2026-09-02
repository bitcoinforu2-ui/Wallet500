# Wallet500 — Measurable vs Rest Experiment

{
  "generated_at": "2026-09-02T08:31:17.204108+00:00",
  "method": "MEASURABLE_VS_REST_BIAS_EXPERIMENT_V1",
  "production_change": false,
  "truth_rule": "Do not interpret measurability as alpha until technical/data-coverage bias is separated from market-feature differences.",
  "tracked_total": 32582,
  "measured_now_n": 341,
  "rest_n": 32241,
  "technical_layer": {
    "measured": {
      "n": 341,
      "pair_locked_n": 341,
      "pair_locked_pct": 100.0,
      "earliest_snapshot_available_n": 341,
      "earliest_snapshot_available_pct": 100.0,
      "current_pair_available_n": 341,
      "current_pair_available_pct": 100.0,
      "chains": {
        "bsc": 121,
        "ethereum": 80,
        "solana": 140
      },
      "measurement_statuses": {
        "VERIFIED_EXACT_PAIR": 341
      }
    },
    "rest": {
      "n": 32241,
      "pair_locked_n": 30417,
      "pair_locked_pct": 94.34,
      "earliest_snapshot_available_n": 21922,
      "earliest_snapshot_available_pct": 67.99,
      "current_pair_available_n": 21923,
      "current_pair_available_pct": 68.0,
      "chains": {
        "bsc": 11705,
        "ethereum": 1067,
        "solana": 19469
      },
      "measurement_statuses": {
        "AWAITING_EXACT_PAIR_OBSERVATION": 30299,
        "UNKNOWN": 69,
        "LEGACY_UNVERIFIABLE_PAIR": 1753,
        "QUARANTINED_NON_EXECUTABLE_PRICE": 120
      }
    },
    "snapshot_coverage_gap_pp": 32.01
  },
  "market_layer_earliest_snapshot_only": {
    "measured": {
      "comparable_n": 341,
      "liquidity_usd_median": 10.23,
      "volume_h1_median": 2848.45,
      "turnover_h1_median": 1.026161,
      "buy_sell_ratio_median": 1.55,
      "txns_h1_median": 37.0
    },
    "rest": {
      "comparable_n": 21922,
      "liquidity_usd_median": 0.0,
      "volume_h1_median": 1452.77,
      "turnover_h1_median": 5.363793,
      "buy_sell_ratio_median": 1.25,
      "txns_h1_median": 30.0
    },
    "measured_to_rest_ratios": {
      "liquidity_median_ratio_measured_to_rest": null,
      "volume_median_ratio_measured_to_rest": 1.960703,
      "turnover_median_ratio_measured_to_rest": 0.191313,
      "buy_sell_ratio_median_ratio_measured_to_rest": 1.24,
      "txns_median_ratio_measured_to_rest": 1.233333
    }
  },
  "interpretation_guard": "Market medians use only each token earliest stored historical observation. Missing-history tokens remain in coverage diagnostics.",
  "status": "ANALYZABLE"
}
