# Wallet500 — Measurable vs Rest Experiment

{
  "generated_at": "2026-09-01T04:07:32.451847+00:00",
  "method": "MEASURABLE_VS_REST_BIAS_EXPERIMENT_V1",
  "production_change": false,
  "truth_rule": "Do not interpret measurability as alpha until technical/data-coverage bias is separated from market-feature differences.",
  "tracked_total": 24550,
  "measured_now_n": 456,
  "rest_n": 24094,
  "technical_layer": {
    "measured": {
      "n": 456,
      "pair_locked_n": 456,
      "pair_locked_pct": 100.0,
      "earliest_snapshot_available_n": 456,
      "earliest_snapshot_available_pct": 100.0,
      "current_pair_available_n": 456,
      "current_pair_available_pct": 100.0,
      "chains": {
        "bsc": 136,
        "ethereum": 113,
        "solana": 207
      },
      "measurement_statuses": {
        "VERIFIED_EXACT_PAIR": 456
      }
    },
    "rest": {
      "n": 24094,
      "pair_locked_n": 22267,
      "pair_locked_pct": 92.42,
      "earliest_snapshot_available_n": 13759,
      "earliest_snapshot_available_pct": 57.11,
      "current_pair_available_n": 13760,
      "current_pair_available_pct": 57.11,
      "chains": {
        "bsc": 8900,
        "ethereum": 836,
        "solana": 14358
      },
      "measurement_statuses": {
        "AWAITING_EXACT_PAIR_OBSERVATION": 22269,
        "UNKNOWN": 69,
        "LEGACY_UNVERIFIABLE_PAIR": 1756
      }
    },
    "snapshot_coverage_gap_pp": 42.89
  },
  "market_layer_earliest_snapshot_only": {
    "measured": {
      "comparable_n": 456,
      "liquidity_usd_median": 0.9,
      "volume_h1_median": 1602.77,
      "turnover_h1_median": 0.265506,
      "buy_sell_ratio_median": 1.246428,
      "txns_h1_median": 29.0
    },
    "rest": {
      "comparable_n": 13759,
      "liquidity_usd_median": 0.0,
      "volume_h1_median": 1319.54,
      "turnover_h1_median": 5.109096,
      "buy_sell_ratio_median": 1.243493,
      "txns_h1_median": 28.0
    },
    "measured_to_rest_ratios": {
      "liquidity_median_ratio_measured_to_rest": null,
      "volume_median_ratio_measured_to_rest": 1.214643,
      "turnover_median_ratio_measured_to_rest": 0.051967,
      "buy_sell_ratio_median_ratio_measured_to_rest": 1.00236,
      "txns_median_ratio_measured_to_rest": 1.035714
    }
  },
  "interpretation_guard": "Market medians use only each token earliest stored historical observation. Missing-history tokens remain in coverage diagnostics.",
  "status": "ANALYZABLE"
}
