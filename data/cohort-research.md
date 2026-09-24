# Wallet500 Cohort Research

Generated: 2026-09-24T09:11:32.464566+00:00
Source snapshot: 2026-09-24T09:05:05.395618+00:00

## Baseline
- N=359 ROI=-0.7607% P/L=$-2.731057

## Best post-hoc counterfactuals (min 5 retained)
- liq>=250k: N=128 ROI=-0.3864% delta=0.3743pp
- turnover<=1: N=193 ROI=-0.4086% delta=0.3521pp
- liq>=500k: N=174 ROI=-0.4421% delta=0.3186pp
- turnover<=2: N=285 ROI=-0.752% delta=0.0087pp
- vol>=50k: N=359 ROI=-0.7607% delta=0.0pp
- liq>=100k: N=232 ROI=-0.7708% delta=-0.0101pp
- liq>=100k & vol>=50k: N=232 ROI=-0.7708% delta=-0.0101pp
- tx>=100: N=328 ROI=-0.861% delta=-0.1003pp
- vol>=25k: N=330 ROI=-0.8817% delta=-0.121pp
- liq>=75k: N=286 ROI=-0.9749% delta=-0.2142pp

## Missed-star scan
- Candidates: 1165
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 71, 'LIQ_LT_15K': 1047, 'VOL_LT_15K': 723, 'TX_LT_50': 588}

Research only; validate prospectively before changing production gates.
