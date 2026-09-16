# Wallet500 Cohort Research

Generated: 2026-09-16T05:06:37.045263+00:00
Source snapshot: 2026-09-16T04:59:58.907211+00:00

## Baseline
- N=359 ROI=-0.8096% P/L=$-2.906568

## Best post-hoc counterfactuals (min 5 retained)
- liq>=250k: N=128 ROI=-0.3864% delta=0.4232pp
- liq>=500k: N=174 ROI=-0.4421% delta=0.3675pp
- turnover<=1: N=193 ROI=-0.4995% delta=0.3101pp
- vol>=50k: N=359 ROI=-0.8096% delta=0.0pp
- turnover<=2: N=285 ROI=-0.8136% delta=-0.004pp
- liq>=100k: N=232 ROI=-0.8465% delta=-0.0369pp
- liq>=100k & vol>=50k: N=232 ROI=-0.8465% delta=-0.0369pp
- tx>=100: N=328 ROI=-0.9145% delta=-0.1049pp
- vol>=25k: N=330 ROI=-0.9349% delta=-0.1253pp
- liq>=75k: N=286 ROI=-1.0362% delta=-0.2266pp

## Missed-star scan
- Candidates: 1165
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 71, 'LIQ_LT_15K': 1047, 'VOL_LT_15K': 723, 'TX_LT_50': 588}

Research only; validate prospectively before changing production gates.
