# Wallet500 Cohort Research

Generated: 2026-09-23T04:07:00.745827+00:00
Source snapshot: 2026-09-23T04:00:43.626693+00:00

## Baseline
- N=359 ROI=-0.7471% P/L=$-2.682078

## Best post-hoc counterfactuals (min 5 retained)
- turnover<=1: N=193 ROI=-0.3832% delta=0.3639pp
- liq>=250k: N=128 ROI=-0.3864% delta=0.3607pp
- liq>=500k: N=174 ROI=-0.4421% delta=0.305pp
- turnover<=2: N=285 ROI=-0.7348% delta=0.0123pp
- vol>=50k: N=359 ROI=-0.7471% delta=0.0pp
- liq>=100k: N=232 ROI=-0.7497% delta=-0.0026pp
- liq>=100k & vol>=50k: N=232 ROI=-0.7497% delta=-0.0026pp
- tx>=100: N=328 ROI=-0.8461% delta=-0.099pp
- vol>=25k: N=330 ROI=-0.8668% delta=-0.1197pp
- liq>=75k: N=286 ROI=-0.9578% delta=-0.2107pp

## Missed-star scan
- Candidates: 1165
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 71, 'LIQ_LT_15K': 1047, 'VOL_LT_15K': 723, 'TX_LT_50': 588}

Research only; validate prospectively before changing production gates.
