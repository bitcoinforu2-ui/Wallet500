# Wallet500 Cohort Research

Generated: 2026-09-21T07:12:54.426813+00:00
Source snapshot: 2026-09-21T07:06:11.483403+00:00

## Baseline
- N=359 ROI=-0.7395% P/L=$-2.654731

## Best post-hoc counterfactuals (min 5 retained)
- turnover<=1: N=193 ROI=-0.369% delta=0.3705pp
- liq>=250k: N=128 ROI=-0.3864% delta=0.3531pp
- liq>=500k: N=174 ROI=-0.4421% delta=0.2974pp
- turnover<=2: N=285 ROI=-0.7253% delta=0.0142pp
- liq>=100k: N=232 ROI=-0.7379% delta=0.0016pp
- liq>=100k & vol>=50k: N=232 ROI=-0.7379% delta=0.0016pp
- vol>=50k: N=359 ROI=-0.7395% delta=0.0pp
- tx>=100: N=328 ROI=-0.8377% delta=-0.0982pp
- vol>=25k: N=330 ROI=-0.8586% delta=-0.1191pp
- liq>=75k: N=286 ROI=-0.9482% delta=-0.2087pp

## Missed-star scan
- Candidates: 1165
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 71, 'LIQ_LT_15K': 1047, 'VOL_LT_15K': 723, 'TX_LT_50': 588}

Research only; validate prospectively before changing production gates.
