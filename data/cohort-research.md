# Wallet500 Cohort Research

Generated: 2026-09-19T14:51:47.658285+00:00
Source snapshot: 2026-09-19T14:45:22.024840+00:00

## Baseline
- N=359 ROI=-0.7147% P/L=$-2.565751

## Best post-hoc counterfactuals (min 5 retained)
- turnover<=1: N=193 ROI=-0.3229% delta=0.3918pp
- liq>=250k: N=128 ROI=-0.3864% delta=0.3283pp
- liq>=500k: N=174 ROI=-0.4421% delta=0.2726pp
- turnover<=2: N=285 ROI=-0.694% delta=0.0207pp
- liq>=100k: N=232 ROI=-0.6996% delta=0.0151pp
- liq>=100k & vol>=50k: N=232 ROI=-0.6996% delta=0.0151pp
- vol>=50k: N=359 ROI=-0.7147% delta=0.0pp
- tx>=100: N=328 ROI=-0.8106% delta=-0.0959pp
- vol>=25k: N=330 ROI=-0.8316% delta=-0.1169pp
- liq>=75k: N=286 ROI=-0.9171% delta=-0.2024pp

## Missed-star scan
- Candidates: 1165
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 71, 'LIQ_LT_15K': 1047, 'VOL_LT_15K': 723, 'TX_LT_50': 588}

Research only; validate prospectively before changing production gates.
