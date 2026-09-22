# Wallet500 Cohort Research

Generated: 2026-09-22T15:55:34.913022+00:00
Source snapshot: 2026-09-22T15:49:01.873966+00:00

## Baseline
- N=359 ROI=-0.744% P/L=$-2.671057

## Best post-hoc counterfactuals (min 5 retained)
- turnover<=1: N=193 ROI=-0.3775% delta=0.3665pp
- liq>=250k: N=128 ROI=-0.3864% delta=0.3576pp
- liq>=500k: N=174 ROI=-0.4421% delta=0.3019pp
- turnover<=2: N=285 ROI=-0.731% delta=0.013pp
- vol>=50k: N=359 ROI=-0.744% delta=0.0pp
- liq>=100k: N=232 ROI=-0.7449% delta=-0.0009pp
- liq>=100k & vol>=50k: N=232 ROI=-0.7449% delta=-0.0009pp
- tx>=100: N=328 ROI=-0.8427% delta=-0.0987pp
- vol>=25k: N=330 ROI=-0.8635% delta=-0.1195pp
- liq>=75k: N=286 ROI=-0.9539% delta=-0.2099pp

## Missed-star scan
- Candidates: 1165
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 71, 'LIQ_LT_15K': 1047, 'VOL_LT_15K': 723, 'TX_LT_50': 588}

Research only; validate prospectively before changing production gates.
