# Wallet500 — Measurable vs Rest Experiment

{
  "generated_at": "2026-09-01T05:40:57.059730+00:00",
  "method": "MEASURABLE_VS_REST_BIAS_EXPERIMENT_V1",
  "production_change": false,
  "truth_rule": "Do not interpret measurability as alpha until technical/data-coverage bias is separated from market-feature differences.",
  "tracked_total": 25022,
  "measured_now_n": 450,
  "rest_n": 24572,
  "technical_layer": {
    "measured": {
      "n": 450,
      "pair_locked_n": 450,
      "pair_locked_pct": 100.0,
      "earliest_snapshot_available_n": 450,
      "earliest_snapshot_available_pct": 100.0,
      "current_pair_available_n": 450,
      "current_pair_available_pct": 100.0,
      "chains": {
        "bsc": 128,
        "solana": 209,
        "ethereum": 113
      },
      "measurement_statuses": {
        "VERIFIED_EXACT_PAIR": 450
      }
    },
    "rest": {
      "n": 24572,
      "pair_locked_n": 22746,
      "pair_locked_pct": 92.57,
      "earliest_snapshot_available_n": 14238,
      "earliest_snapshot_available_pct": 57.94,
      "current_pair_available_n": 14239,
      "current_pair_available_pct": 57.95,
      "chains": {
        "bsc": 9058,
        "ethereum": 850,
        "solana": 14664
      },
      "measurement_statuses": {
        "AWAITING_EXACT_PAIR_OBSERVATION": 22748,
        "UNKNOWN": 69,
        "LEGACY_UNVERIFIABLE_PAIR": 1755
      }
    },
    "snapshot_coverage_gap_pp": 42.06
  },
  "market_layer_earliest_snapshot_only": {
    "measured": {
      "comparable_n": 450,
      "liquidity_usd_median": 0.08,
      "volume_h1_median": 1219.81,
      "turnover_h1_median": 0.259208,
      "buy_sell_ratio_median": 1.362373,
      "txns_h1_median": 23.0
    },
    "rest": {
      "comparable_n": 14238,
      "liquidity_usd_median": 0.0,
      "volume_h1_median": 1324.41,
      "turnover_h1_median": 5.032402,
      "buy_sell_ratio_median": 1.240976,
      "txns_h1_median": 29.0
    },
    "measured_to_rest_ratios": {
      "liquidity_median_ratio_measured_to_rest": null,
      "volume_median_ratio_measured_to_rest": 0.921021,
      "turnover_median_ratio_measured_to_rest": 0.051508,
      "buy_sell_ratio_median_ratio_measured_to_rest": 1.097824,
      "txns_median_ratio_measured_to_rest": 0.793103
    }
  },
  "interpretation_guard": "Market medians use only each token earliest stored historical observation. Missing-history tokens remain in coverage diagnostics.",
  "status": "ANALYZABLE"
}
