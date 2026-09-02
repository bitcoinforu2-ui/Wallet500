# Wallet500 — Measurable vs Rest Experiment

{
  "generated_at": "2026-09-02T07:30:08.442191+00:00",
  "method": "MEASURABLE_VS_REST_BIAS_EXPERIMENT_V1",
  "production_change": false,
  "truth_rule": "Do not interpret measurability as alpha until technical/data-coverage bias is separated from market-feature differences.",
  "tracked_total": 32312,
  "measured_now_n": 318,
  "rest_n": 31994,
  "technical_layer": {
    "measured": {
      "n": 318,
      "pair_locked_n": 318,
      "pair_locked_pct": 100.0,
      "earliest_snapshot_available_n": 318,
      "earliest_snapshot_available_pct": 100.0,
      "current_pair_available_n": 318,
      "current_pair_available_pct": 100.0,
      "chains": {
        "bsc": 89,
        "ethereum": 85,
        "solana": 144
      },
      "measurement_statuses": {
        "VERIFIED_EXACT_PAIR": 318
      }
    },
    "rest": {
      "n": 31994,
      "pair_locked_n": 30170,
      "pair_locked_pct": 94.3,
      "earliest_snapshot_available_n": 21675,
      "earliest_snapshot_available_pct": 67.75,
      "current_pair_available_n": 21676,
      "current_pair_available_pct": 67.75,
      "chains": {
        "bsc": 11624,
        "ethereum": 1061,
        "solana": 19309
      },
      "measurement_statuses": {
        "AWAITING_EXACT_PAIR_OBSERVATION": 30047,
        "UNKNOWN": 69,
        "LEGACY_UNVERIFIABLE_PAIR": 1753,
        "QUARANTINED_NON_EXECUTABLE_PRICE": 125
      }
    },
    "snapshot_coverage_gap_pp": 32.25
  },
  "market_layer_earliest_snapshot_only": {
    "measured": {
      "comparable_n": 318,
      "liquidity_usd_median": 2905.29,
      "volume_h1_median": 2255.47,
      "turnover_h1_median": 0.465156,
      "buy_sell_ratio_median": 1.464687,
      "txns_h1_median": 33.0
    },
    "rest": {
      "comparable_n": 21675,
      "liquidity_usd_median": 0.0,
      "volume_h1_median": 1449.27,
      "turnover_h1_median": 5.287317,
      "buy_sell_ratio_median": 1.25,
      "txns_h1_median": 30.0
    },
    "measured_to_rest_ratios": {
      "liquidity_median_ratio_measured_to_rest": null,
      "volume_median_ratio_measured_to_rest": 1.55628,
      "turnover_median_ratio_measured_to_rest": 0.087976,
      "buy_sell_ratio_median_ratio_measured_to_rest": 1.17175,
      "txns_median_ratio_measured_to_rest": 1.1
    }
  },
  "interpretation_guard": "Market medians use only each token earliest stored historical observation. Missing-history tokens remain in coverage diagnostics.",
  "status": "ANALYZABLE"
}
