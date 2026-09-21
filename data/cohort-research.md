# Wallet500 Cohort Research

Generated: 2026-09-21T10:39:57.581383+00:00
Source snapshot: 2026-09-21T10:33:43.609908+00:00

## Baseline
- N=359 ROI=-0.7374% P/L=$-2.647384

## Best post-hoc counterfactuals (min 5 retained)
- turnover<=1: N=193 ROI=-0.3652% delta=0.3722pp
- liq>=250k: N=128 ROI=-0.3864% delta=0.351pp
- liq>=500k: N=174 ROI=-0.4421% delta=0.2953pp
- turnover<=2: N=285 ROI=-0.7227% delta=0.0147pp
- liq>=100k: N=232 ROI=-0.7347% delta=0.0027pp
- liq>=100k & vol>=50k: N=232 ROI=-0.7347% delta=0.0027pp
- vol>=50k: N=359 ROI=-0.7374% delta=0.0pp
- tx>=100: N=328 ROI=-0.8355% delta=-0.0981pp
- vol>=25k: N=330 ROI=-0.8563% delta=-0.1189pp
- liq>=75k: N=286 ROI=-0.9456% delta=-0.2082pp

## Missed-star scan
- Candidates: 1165
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 71, 'LIQ_LT_15K': 1047, 'VOL_LT_15K': 723, 'TX_LT_50': 588}

Research only; validate prospectively before changing production gates.
