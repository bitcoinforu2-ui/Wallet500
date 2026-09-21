# Wallet500 Cohort Research

Generated: 2026-09-21T01:27:53.026129+00:00
Source snapshot: 2026-09-21T01:21:35.874141+00:00

## Baseline
- N=359 ROI=-0.7378% P/L=$-2.648608

## Best post-hoc counterfactuals (min 5 retained)
- turnover<=1: N=193 ROI=-0.3659% delta=0.3719pp
- liq>=250k: N=128 ROI=-0.3864% delta=0.3514pp
- liq>=500k: N=174 ROI=-0.4421% delta=0.2957pp
- turnover<=2: N=285 ROI=-0.7231% delta=0.0147pp
- liq>=100k: N=232 ROI=-0.7353% delta=0.0025pp
- liq>=100k & vol>=50k: N=232 ROI=-0.7353% delta=0.0025pp
- vol>=50k: N=359 ROI=-0.7378% delta=0.0pp
- tx>=100: N=328 ROI=-0.8359% delta=-0.0981pp
- vol>=25k: N=330 ROI=-0.8567% delta=-0.1189pp
- liq>=75k: N=286 ROI=-0.9461% delta=-0.2083pp

## Missed-star scan
- Candidates: 1165
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 71, 'LIQ_LT_15K': 1047, 'VOL_LT_15K': 723, 'TX_LT_50': 588}

Research only; validate prospectively before changing production gates.
