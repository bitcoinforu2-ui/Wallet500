# Wallet500 Cohort Research

Generated: 2026-09-17T05:39:04.413226+00:00
Source snapshot: 2026-09-17T05:32:34.962255+00:00

## Baseline
- N=359 ROI=-0.8109% P/L=$-2.911057

## Best post-hoc counterfactuals (min 5 retained)
- liq>=250k: N=128 ROI=-0.3864% delta=0.4245pp
- liq>=500k: N=174 ROI=-0.4421% delta=0.3688pp
- turnover<=1: N=193 ROI=-0.5018% delta=0.3091pp
- vol>=50k: N=359 ROI=-0.8109% delta=0.0pp
- turnover<=2: N=285 ROI=-0.8152% delta=-0.0043pp
- liq>=100k: N=232 ROI=-0.8484% delta=-0.0375pp
- liq>=100k & vol>=50k: N=232 ROI=-0.8484% delta=-0.0375pp
- tx>=100: N=328 ROI=-0.9159% delta=-0.105pp
- vol>=25k: N=330 ROI=-0.9362% delta=-0.1253pp
- liq>=75k: N=286 ROI=-1.0378% delta=-0.2269pp

## Missed-star scan
- Candidates: 1165
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 71, 'LIQ_LT_15K': 1047, 'VOL_LT_15K': 723, 'TX_LT_50': 588}

Research only; validate prospectively before changing production gates.
