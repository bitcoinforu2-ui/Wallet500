# Wallet500 — Measurable vs Rest Experiment

{
  "generated_at": "2026-08-31T15:06:29.460204+00:00",
  "method": "MEASURABLE_VS_REST_BIAS_EXPERIMENT_V1",
  "production_change": false,
  "truth_rule": "Do not interpret measurability as alpha until technical/data-coverage bias is separated from market-feature differences.",
  "tracked_total": 21012,
  "measured_now_n": 445,
  "rest_n": 20567,
  "technical_layer": {
    "measured": {
      "n": 445,
      "pair_locked_n": 445,
      "pair_locked_pct": 100.0,
      "earliest_snapshot_available_n": 445,
      "earliest_snapshot_available_pct": 100.0,
      "current_pair_available_n": 445,
      "current_pair_available_pct": 100.0,
      "chains": {
        "ethereum": 113,
        "bsc": 125,
        "solana": 207
      },
      "measurement_statuses": {
        "VERIFIED_EXACT_PAIR": 445
      }
    },
    "rest": {
      "n": 20567,
      "pair_locked_n": 18737,
      "pair_locked_pct": 91.1,
      "earliest_snapshot_available_n": 10218,
      "earliest_snapshot_available_pct": 49.68,
      "current_pair_available_n": 10219,
      "current_pair_available_pct": 49.69,
      "chains": {
        "bsc": 7764,
        "ethereum": 718,
        "solana": 12085
      },
      "measurement_statuses": {
        "AWAITING_EXACT_PAIR_OBSERVATION": 18739,
        "UNKNOWN": 69,
        "LEGACY_UNVERIFIABLE_PAIR": 1759
      }
    },
    "snapshot_coverage_gap_pp": 50.32
  },
  "market_layer_earliest_snapshot_only": {
    "measured": {
      "comparable_n": 445,
      "liquidity_usd_median": 0.12,
      "volume_h1_median": 1981.53,
      "turnover_h1_median": 0.750388,
      "buy_sell_ratio_median": 1.315789,
      "txns_h1_median": 29.0
    },
    "rest": {
      "comparable_n": 10218,
      "liquidity_usd_median": 0.0,
      "volume_h1_median": 1297.92,
      "turnover_h1_median": 4.170407,
      "buy_sell_ratio_median": 1.25,
      "txns_h1_median": 28.0
    },
    "measured_to_rest_ratios": {
      "liquidity_median_ratio_measured_to_rest": null,
      "volume_median_ratio_measured_to_rest": 1.526697,
      "turnover_median_ratio_measured_to_rest": 0.179932,
      "buy_sell_ratio_median_ratio_measured_to_rest": 1.052631,
      "txns_median_ratio_measured_to_rest": 1.035714
    }
  },
  "interpretation_guard": "Market medians use only each token earliest stored historical observation. Missing-history tokens remain in coverage diagnostics.",
  "status": "ANALYZABLE"
}
