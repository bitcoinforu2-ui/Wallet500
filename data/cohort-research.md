# Wallet500 Cohort Research

Generated: 2026-09-19T12:45:35.865444+00:00
Source snapshot: 2026-09-19T12:39:15.855900+00:00

## Baseline
- N=359 ROI=-0.6981% P/L=$-2.506159

## Best post-hoc counterfactuals (min 5 retained)
- turnover<=1: N=193 ROI=-0.292% delta=0.4061pp
- liq>=250k: N=128 ROI=-0.3864% delta=0.3117pp
- liq>=500k: N=174 ROI=-0.4421% delta=0.256pp
- turnover<=2: N=285 ROI=-0.6731% delta=0.025pp
- liq>=100k: N=232 ROI=-0.6739% delta=0.0242pp
- liq>=100k & vol>=50k: N=232 ROI=-0.6739% delta=0.0242pp
- vol>=50k: N=359 ROI=-0.6981% delta=0.0pp
- tx>=100: N=328 ROI=-0.7924% delta=-0.0943pp
- vol>=25k: N=330 ROI=-0.8135% delta=-0.1154pp
- tx>=500: N=184 ROI=-0.8925% delta=-0.1944pp

## Missed-star scan
- Candidates: 1165
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 71, 'LIQ_LT_15K': 1047, 'VOL_LT_15K': 723, 'TX_LT_50': 588}

Research only; validate prospectively before changing production gates.
