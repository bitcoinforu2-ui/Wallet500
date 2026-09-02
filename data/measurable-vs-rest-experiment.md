# Wallet500 — Measurable vs Rest Experiment

{
  "generated_at": "2026-09-02T06:23:49.131315+00:00",
  "method": "MEASURABLE_VS_REST_BIAS_EXPERIMENT_V1",
  "production_change": false,
  "truth_rule": "Do not interpret measurability as alpha until technical/data-coverage bias is separated from market-feature differences.",
  "tracked_total": 31976,
  "measured_now_n": 341,
  "rest_n": 31635,
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
        "bsc": 97,
        "ethereum": 93,
        "solana": 151
      },
      "measurement_statuses": {
        "VERIFIED_EXACT_PAIR": 341
      }
    },
    "rest": {
      "n": 31635,
      "pair_locked_n": 29811,
      "pair_locked_pct": 94.23,
      "earliest_snapshot_available_n": 21315,
      "earliest_snapshot_available_pct": 67.38,
      "current_pair_available_n": 21316,
      "current_pair_available_pct": 67.38,
      "chains": {
        "bsc": 11506,
        "ethereum": 1048,
        "solana": 19081
      },
      "measurement_statuses": {
        "AWAITING_EXACT_PAIR_OBSERVATION": 29701,
        "UNKNOWN": 69,
        "LEGACY_UNVERIFIABLE_PAIR": 1753,
        "QUARANTINED_NON_EXECUTABLE_PRICE": 112
      }
    },
    "snapshot_coverage_gap_pp": 32.62
  },
  "market_layer_earliest_snapshot_only": {
    "measured": {
      "comparable_n": 341,
      "liquidity_usd_median": 2055.01,
      "volume_h1_median": 3000.0,
      "turnover_h1_median": 0.784527,
      "buy_sell_ratio_median": 1.4375,
      "txns_h1_median": 39.0
    },
    "rest": {
      "comparable_n": 21315,
      "liquidity_usd_median": 0.0,
      "volume_h1_median": 1444.53,
      "turnover_h1_median": 5.339198,
      "buy_sell_ratio_median": 1.25,
      "txns_h1_median": 30.0
    },
    "measured_to_rest_ratios": {
      "liquidity_median_ratio_measured_to_rest": null,
      "volume_median_ratio_measured_to_rest": 2.0768,
      "turnover_median_ratio_measured_to_rest": 0.146937,
      "buy_sell_ratio_median_ratio_measured_to_rest": 1.15,
      "txns_median_ratio_measured_to_rest": 1.3
    }
  },
  "interpretation_guard": "Market medians use only each token earliest stored historical observation. Missing-history tokens remain in coverage diagnostics.",
  "status": "ANALYZABLE"
}
