# Wallet500 — Measurable vs Rest Experiment

{
  "generated_at": "2026-09-01T04:40:39.216750+00:00",
  "method": "MEASURABLE_VS_REST_BIAS_EXPERIMENT_V1",
  "production_change": false,
  "truth_rule": "Do not interpret measurability as alpha until technical/data-coverage bias is separated from market-feature differences.",
  "tracked_total": 24673,
  "measured_now_n": 456,
  "rest_n": 24217,
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
        "bsc": 135,
        "solana": 208,
        "ethereum": 113
      },
      "measurement_statuses": {
        "VERIFIED_EXACT_PAIR": 456
      }
    },
    "rest": {
      "n": 24217,
      "pair_locked_n": 22391,
      "pair_locked_pct": 92.46,
      "earliest_snapshot_available_n": 13883,
      "earliest_snapshot_available_pct": 57.33,
      "current_pair_available_n": 13884,
      "current_pair_available_pct": 57.33,
      "chains": {
        "bsc": 8942,
        "ethereum": 841,
        "solana": 14434
      },
      "measurement_statuses": {
        "AWAITING_EXACT_PAIR_OBSERVATION": 22393,
        "UNKNOWN": 69,
        "LEGACY_UNVERIFIABLE_PAIR": 1755
      }
    },
    "snapshot_coverage_gap_pp": 42.67
  },
  "market_layer_earliest_snapshot_only": {
    "measured": {
      "comparable_n": 456,
      "liquidity_usd_median": 0.09,
      "volume_h1_median": 1288.23,
      "turnover_h1_median": 0.2876,
      "buy_sell_ratio_median": 1.309741,
      "txns_h1_median": 24.5
    },
    "rest": {
      "comparable_n": 13883,
      "liquidity_usd_median": 0.0,
      "volume_h1_median": 1333.56,
      "turnover_h1_median": 5.032402,
      "buy_sell_ratio_median": 1.241042,
      "txns_h1_median": 29.0
    },
    "measured_to_rest_ratios": {
      "liquidity_median_ratio_measured_to_rest": null,
      "volume_median_ratio_measured_to_rest": 0.966008,
      "turnover_median_ratio_measured_to_rest": 0.05715,
      "buy_sell_ratio_median_ratio_measured_to_rest": 1.055356,
      "txns_median_ratio_measured_to_rest": 0.844828
    }
  },
  "interpretation_guard": "Market medians use only each token earliest stored historical observation. Missing-history tokens remain in coverage diagnostics.",
  "status": "ANALYZABLE"
}
