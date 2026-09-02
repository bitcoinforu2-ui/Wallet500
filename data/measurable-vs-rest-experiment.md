# Wallet500 — Measurable vs Rest Experiment

{
  "generated_at": "2026-09-02T01:04:22.719837+00:00",
  "method": "MEASURABLE_VS_REST_BIAS_EXPERIMENT_V1",
  "production_change": false,
  "truth_rule": "Do not interpret measurability as alpha until technical/data-coverage bias is separated from market-feature differences.",
  "tracked_total": 30687,
  "measured_now_n": 416,
  "rest_n": 30271,
  "technical_layer": {
    "measured": {
      "n": 416,
      "pair_locked_n": 416,
      "pair_locked_pct": 100.0,
      "earliest_snapshot_available_n": 416,
      "earliest_snapshot_available_pct": 100.0,
      "current_pair_available_n": 416,
      "current_pair_available_pct": 100.0,
      "chains": {
        "bsc": 102,
        "solana": 208,
        "ethereum": 106
      },
      "measurement_statuses": {
        "VERIFIED_EXACT_PAIR": 416
      }
    },
    "rest": {
      "n": 30271,
      "pair_locked_n": 28447,
      "pair_locked_pct": 93.97,
      "earliest_snapshot_available_n": 19950,
      "earliest_snapshot_available_pct": 65.9,
      "current_pair_available_n": 19951,
      "current_pair_available_pct": 65.91,
      "chains": {
        "bsc": 10996,
        "ethereum": 1000,
        "solana": 18275
      },
      "measurement_statuses": {
        "AWAITING_EXACT_PAIR_OBSERVATION": 28449,
        "UNKNOWN": 69,
        "LEGACY_UNVERIFIABLE_PAIR": 1753
      }
    },
    "snapshot_coverage_gap_pp": 34.1
  },
  "market_layer_earliest_snapshot_only": {
    "measured": {
      "comparable_n": 416,
      "liquidity_usd_median": 0.125,
      "volume_h1_median": 1446.725,
      "turnover_h1_median": 0.373596,
      "buy_sell_ratio_median": 1.301163,
      "txns_h1_median": 24.5
    },
    "rest": {
      "comparable_n": 19950,
      "liquidity_usd_median": 0.0,
      "volume_h1_median": 1410.575,
      "turnover_h1_median": 5.131931,
      "buy_sell_ratio_median": 1.25,
      "txns_h1_median": 30.0
    },
    "measured_to_rest_ratios": {
      "liquidity_median_ratio_measured_to_rest": null,
      "volume_median_ratio_measured_to_rest": 1.025628,
      "turnover_median_ratio_measured_to_rest": 0.072798,
      "buy_sell_ratio_median_ratio_measured_to_rest": 1.04093,
      "txns_median_ratio_measured_to_rest": 0.816667
    }
  },
  "interpretation_guard": "Market medians use only each token earliest stored historical observation. Missing-history tokens remain in coverage diagnostics.",
  "status": "ANALYZABLE"
}
