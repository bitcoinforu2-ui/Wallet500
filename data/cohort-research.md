# Wallet500 Cohort Research

Generated: 2026-09-19T04:40:47.075825+00:00
Source snapshot: 2026-09-19T04:34:17.591685+00:00

## Baseline
- N=359 ROI=-0.7548% P/L=$-2.709833

## Best post-hoc counterfactuals (min 5 retained)
- liq>=250k: N=128 ROI=-0.3864% delta=0.3684pp
- turnover<=1: N=193 ROI=-0.3976% delta=0.3572pp
- liq>=500k: N=174 ROI=-0.4421% delta=0.3127pp
- turnover<=2: N=285 ROI=-0.7446% delta=0.0102pp
- vol>=50k: N=359 ROI=-0.7548% delta=0.0pp
- liq>=100k: N=232 ROI=-0.7617% delta=-0.0069pp
- liq>=100k & vol>=50k: N=232 ROI=-0.7617% delta=-0.0069pp
- tx>=100: N=328 ROI=-0.8545% delta=-0.0997pp
- vol>=25k: N=330 ROI=-0.8752% delta=-0.1204pp
- liq>=75k: N=286 ROI=-0.9675% delta=-0.2127pp

## Missed-star scan
- Candidates: 1165
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 71, 'LIQ_LT_15K': 1047, 'VOL_LT_15K': 723, 'TX_LT_50': 588}

Research only; validate prospectively before changing production gates.
