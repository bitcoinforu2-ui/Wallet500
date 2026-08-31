# Wallet500 — Measurable vs Rest Experiment

{
  "generated_at": "2026-08-31T04:06:34.726743+00:00",
  "method": "MEASURABLE_VS_REST_BIAS_EXPERIMENT_V1",
  "production_change": false,
  "truth_rule": "Do not interpret measurability as alpha until technical/data-coverage bias is separated from market-feature differences.",
  "tracked_total": 18109,
  "measured_now_n": 465,
  "rest_n": 17644,
  "technical_layer": {
    "measured": {
      "n": 465,
      "pair_locked_n": 465,
      "pair_locked_pct": 100.0,
      "earliest_snapshot_available_n": 465,
      "earliest_snapshot_available_pct": 100.0,
      "current_pair_available_n": 465,
      "current_pair_available_pct": 100.0,
      "chains": {
        "bsc": 144,
        "ethereum": 116,
        "solana": 205
      },
      "measurement_statuses": {
        "VERIFIED_EXACT_PAIR": 465
      }
    },
    "rest": {
      "n": 17644,
      "pair_locked_n": 15814,
      "pair_locked_pct": 89.63,
      "earliest_snapshot_available_n": 7286,
      "earliest_snapshot_available_pct": 41.29,
      "current_pair_available_n": 7287,
      "current_pair_available_pct": 41.3,
      "chains": {
        "bsc": 6678,
        "ethereum": 656,
        "solana": 10310
      },
      "measurement_statuses": {
        "AWAITING_EXACT_PAIR_OBSERVATION": 15816,
        "UNKNOWN": 69,
        "LEGACY_UNVERIFIABLE_PAIR": 1759
      }
    },
    "snapshot_coverage_gap_pp": 58.71
  },
  "market_layer_earliest_snapshot_only": {
    "measured": {
      "comparable_n": 465,
      "liquidity_usd_median": 0.11,
      "volume_h1_median": 1712.43,
      "turnover_h1_median": 0.41667,
      "buy_sell_ratio_median": 1.318182,
      "txns_h1_median": 27.0
    },
    "rest": {
      "comparable_n": 7286,
      "liquidity_usd_median": 0.0,
      "volume_h1_median": 1140.445,
      "turnover_h1_median": 2.869372,
      "buy_sell_ratio_median": 1.243069,
      "txns_h1_median": 25.0
    },
    "measured_to_rest_ratios": {
      "liquidity_median_ratio_measured_to_rest": null,
      "volume_median_ratio_measured_to_rest": 1.501545,
      "turnover_median_ratio_measured_to_rest": 0.145213,
      "buy_sell_ratio_median_ratio_measured_to_rest": 1.060425,
      "txns_median_ratio_measured_to_rest": 1.08
    }
  },
  "interpretation_guard": "Market medians use only each token earliest stored historical observation. Missing-history tokens remain in coverage diagnostics.",
  "status": "ANALYZABLE"
}
