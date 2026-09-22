# Wallet500 Cohort Research

Generated: 2026-09-22T03:29:08.127766+00:00
Source snapshot: 2026-09-22T03:21:57.989094+00:00

## Baseline
- N=359 ROI=-0.7371% P/L=$-2.646159

## Best post-hoc counterfactuals (min 5 retained)
- turnover<=1: N=193 ROI=-0.3646% delta=0.3725pp
- liq>=250k: N=128 ROI=-0.3864% delta=0.3507pp
- liq>=500k: N=174 ROI=-0.4421% delta=0.295pp
- turnover<=2: N=285 ROI=-0.7222% delta=0.0149pp
- liq>=100k: N=232 ROI=-0.7342% delta=0.0029pp
- liq>=100k & vol>=50k: N=232 ROI=-0.7342% delta=0.0029pp
- vol>=50k: N=359 ROI=-0.7371% delta=0.0pp
- tx>=100: N=328 ROI=-0.8351% delta=-0.098pp
- vol>=25k: N=330 ROI=-0.856% delta=-0.1189pp
- liq>=75k: N=286 ROI=-0.9452% delta=-0.2081pp

## Missed-star scan
- Candidates: 1165
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 71, 'LIQ_LT_15K': 1047, 'VOL_LT_15K': 723, 'TX_LT_50': 588}

Research only; validate prospectively before changing production gates.
