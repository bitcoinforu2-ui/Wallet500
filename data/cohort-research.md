# Wallet500 Cohort Research

Generated: 2026-09-19T02:27:21.400942+00:00
Source snapshot: 2026-09-19T02:20:17.387345+00:00

## Baseline
- N=359 ROI=-0.785% P/L=$-2.817996

## Best post-hoc counterfactuals (min 5 retained)
- liq>=250k: N=128 ROI=-0.3864% delta=0.3986pp
- liq>=500k: N=174 ROI=-0.4421% delta=0.3429pp
- turnover<=1: N=193 ROI=-0.4536% delta=0.3314pp
- turnover<=2: N=285 ROI=-0.7825% delta=0.0025pp
- vol>=50k: N=359 ROI=-0.785% delta=0.0pp
- liq>=100k: N=232 ROI=-0.8083% delta=-0.0233pp
- liq>=100k & vol>=50k: N=232 ROI=-0.8083% delta=-0.0233pp
- tx>=100: N=328 ROI=-0.8875% delta=-0.1025pp
- vol>=25k: N=330 ROI=-0.908% delta=-0.123pp
- liq>=75k: N=286 ROI=-1.0053% delta=-0.2203pp

## Missed-star scan
- Candidates: 1165
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 71, 'LIQ_LT_15K': 1047, 'VOL_LT_15K': 723, 'TX_LT_50': 588}

Research only; validate prospectively before changing production gates.
