# Wallet500 — Measurable vs Rest Experiment

{
  "generated_at": "2026-08-31T20:08:00.936372+00:00",
  "method": "MEASURABLE_VS_REST_BIAS_EXPERIMENT_V1",
  "production_change": false,
  "truth_rule": "Do not interpret measurability as alpha until technical/data-coverage bias is separated from market-feature differences.",
  "tracked_total": 22436,
  "measured_now_n": 403,
  "rest_n": 22033,
  "technical_layer": {
    "measured": {
      "n": 403,
      "pair_locked_n": 403,
      "pair_locked_pct": 100.0,
      "earliest_snapshot_available_n": 403,
      "earliest_snapshot_available_pct": 100.0,
      "current_pair_available_n": 403,
      "current_pair_available_pct": 100.0,
      "chains": {
        "bsc": 82,
        "ethereum": 114,
        "solana": 207
      },
      "measurement_statuses": {
        "VERIFIED_EXACT_PAIR": 403
      }
    },
    "rest": {
      "n": 22033,
      "pair_locked_n": 20204,
      "pair_locked_pct": 91.7,
      "earliest_snapshot_available_n": 11691,
      "earliest_snapshot_available_pct": 53.06,
      "current_pair_available_n": 11692,
      "current_pair_available_pct": 53.07,
      "chains": {
        "bsc": 8302,
        "ethereum": 763,
        "solana": 12968
      },
      "measurement_statuses": {
        "AWAITING_EXACT_PAIR_OBSERVATION": 20206,
        "UNKNOWN": 69,
        "LEGACY_UNVERIFIABLE_PAIR": 1758
      }
    },
    "snapshot_coverage_gap_pp": 46.94
  },
  "market_layer_earliest_snapshot_only": {
    "measured": {
      "comparable_n": 403,
      "liquidity_usd_median": 7.68,
      "volume_h1_median": 947.62,
      "turnover_h1_median": 0.215311,
      "buy_sell_ratio_median": 1.235294,
      "txns_h1_median": 22.0
    },
    "rest": {
      "comparable_n": 11691,
      "liquidity_usd_median": 0.0,
      "volume_h1_median": 1352.09,
      "turnover_h1_median": 5.117485,
      "buy_sell_ratio_median": 1.243697,
      "txns_h1_median": 28.0
    },
    "measured_to_rest_ratios": {
      "liquidity_median_ratio_measured_to_rest": null,
      "volume_median_ratio_measured_to_rest": 0.700856,
      "turnover_median_ratio_measured_to_rest": 0.042074,
      "buy_sell_ratio_median_ratio_measured_to_rest": 0.993244,
      "txns_median_ratio_measured_to_rest": 0.785714
    }
  },
  "interpretation_guard": "Market medians use only each token earliest stored historical observation. Missing-history tokens remain in coverage diagnostics.",
  "status": "ANALYZABLE"
}
