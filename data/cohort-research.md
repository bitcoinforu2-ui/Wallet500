# Wallet500 Cohort Research

Generated: 2026-09-19T15:05:57.217843+00:00
Source snapshot: 2026-09-19T14:59:23.012276+00:00

## Baseline
- N=359 ROI=-0.7157% P/L=$-2.569425

## Best post-hoc counterfactuals (min 5 retained)
- turnover<=1: N=193 ROI=-0.3248% delta=0.3909pp
- liq>=250k: N=128 ROI=-0.3864% delta=0.3293pp
- liq>=500k: N=174 ROI=-0.4421% delta=0.2736pp
- turnover<=2: N=285 ROI=-0.6953% delta=0.0204pp
- liq>=100k: N=232 ROI=-0.7011% delta=0.0146pp
- liq>=100k & vol>=50k: N=232 ROI=-0.7011% delta=0.0146pp
- vol>=50k: N=359 ROI=-0.7157% delta=0.0pp
- tx>=100: N=328 ROI=-0.8117% delta=-0.096pp
- vol>=25k: N=330 ROI=-0.8327% delta=-0.117pp
- liq>=75k: N=286 ROI=-0.9184% delta=-0.2027pp

## Missed-star scan
- Candidates: 1165
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 71, 'LIQ_LT_15K': 1047, 'VOL_LT_15K': 723, 'TX_LT_50': 588}

Research only; validate prospectively before changing production gates.
