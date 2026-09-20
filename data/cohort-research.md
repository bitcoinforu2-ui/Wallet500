# Wallet500 Cohort Research

Generated: 2026-09-20T10:26:29.914029+00:00
Source snapshot: 2026-09-20T10:20:05.438228+00:00

## Baseline
- N=359 ROI=-1.0319% P/L=$-3.704527

## Best post-hoc counterfactuals (min 5 retained)
- liq>=250k: N=128 ROI=-0.3864% delta=0.6455pp
- turnover<=1: N=193 ROI=-0.3948% delta=0.6371pp
- liq>=500k: N=174 ROI=-0.4421% delta=0.5898pp
- liq>=100k: N=232 ROI=-0.7594% delta=0.2725pp
- liq>=100k & vol>=50k: N=232 ROI=-0.7594% delta=0.2725pp
- liq>=75k: N=286 ROI=-0.9656% delta=0.0663pp
- tx>=500: N=184 ROI=-1.0003% delta=0.0316pp
- tx>=250: N=283 ROI=-1.0037% delta=0.0282pp
- vol>=50k: N=359 ROI=-1.0319% delta=0.0pp
- liq>=100k & tx>=250: N=182 ROI=-1.0427% delta=-0.0108pp

## Missed-star scan
- Candidates: 1165
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 71, 'LIQ_LT_15K': 1047, 'VOL_LT_15K': 723, 'TX_LT_50': 588}

Research only; validate prospectively before changing production gates.
