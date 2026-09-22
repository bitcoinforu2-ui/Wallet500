# Wallet500 Cohort Research

Generated: 2026-09-22T09:09:49.885789+00:00
Source snapshot: 2026-09-22T09:02:57.310071+00:00

## Baseline
- N=359 ROI=-0.7421% P/L=$-2.664119

## Best post-hoc counterfactuals (min 5 retained)
- turnover<=1: N=193 ROI=-0.3739% delta=0.3682pp
- liq>=250k: N=128 ROI=-0.3864% delta=0.3557pp
- liq>=500k: N=174 ROI=-0.4421% delta=0.3pp
- turnover<=2: N=285 ROI=-0.7285% delta=0.0136pp
- liq>=100k: N=232 ROI=-0.742% delta=0.0001pp
- liq>=100k & vol>=50k: N=232 ROI=-0.742% delta=0.0001pp
- vol>=50k: N=359 ROI=-0.7421% delta=0.0pp
- tx>=100: N=328 ROI=-0.8406% delta=-0.0985pp
- vol>=25k: N=330 ROI=-0.8614% delta=-0.1193pp
- liq>=75k: N=286 ROI=-0.9515% delta=-0.2094pp

## Missed-star scan
- Candidates: 1165
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 71, 'LIQ_LT_15K': 1047, 'VOL_LT_15K': 723, 'TX_LT_50': 588}

Research only; validate prospectively before changing production gates.
