# Wallet500 Cohort Research

Generated: 2026-09-25T10:09:40.664291+00:00
Source snapshot: 2026-09-25T10:03:30.502861+00:00

## Baseline
- N=359 ROI=-0.7745% P/L=$-2.780445

## Best post-hoc counterfactuals (min 5 retained)
- liq>=250k: N=128 ROI=-0.3864% delta=0.3881pp
- turnover<=1: N=193 ROI=-0.4342% delta=0.3403pp
- liq>=500k: N=174 ROI=-0.4421% delta=0.3324pp
- turnover<=2: N=285 ROI=-0.7694% delta=0.0051pp
- vol>=50k: N=359 ROI=-0.7745% delta=0.0pp
- liq>=100k: N=232 ROI=-0.7921% delta=-0.0176pp
- liq>=100k & vol>=50k: N=232 ROI=-0.7921% delta=-0.0176pp
- tx>=100: N=328 ROI=-0.8761% delta=-0.1016pp
- vol>=25k: N=330 ROI=-0.8966% delta=-0.1221pp
- liq>=75k: N=286 ROI=-0.9922% delta=-0.2177pp

## Missed-star scan
- Candidates: 1165
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 71, 'LIQ_LT_15K': 1047, 'VOL_LT_15K': 723, 'TX_LT_50': 588}

Research only; validate prospectively before changing production gates.
