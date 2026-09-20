# Wallet500 Cohort Research

Generated: 2026-09-20T07:37:39.419084+00:00
Source snapshot: 2026-09-20T07:31:27.446884+00:00

## Baseline
- N=359 ROI=-1.0284% P/L=$-3.691874

## Best post-hoc counterfactuals (min 5 retained)
- liq>=250k: N=128 ROI=-0.3864% delta=0.642pp
- turnover<=1: N=193 ROI=-0.3883% delta=0.6401pp
- liq>=500k: N=174 ROI=-0.4421% delta=0.5863pp
- liq>=100k: N=232 ROI=-0.7539% delta=0.2745pp
- liq>=100k & vol>=50k: N=232 ROI=-0.7539% delta=0.2745pp
- liq>=75k: N=286 ROI=-0.9612% delta=0.0672pp
- tx>=500: N=184 ROI=-0.9935% delta=0.0349pp
- tx>=250: N=283 ROI=-0.9992% delta=0.0292pp
- vol>=50k: N=359 ROI=-1.0284% delta=0.0pp
- liq>=100k & tx>=250: N=182 ROI=-1.0358% delta=-0.0074pp

## Missed-star scan
- Candidates: 1165
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 71, 'LIQ_LT_15K': 1047, 'VOL_LT_15K': 723, 'TX_LT_50': 588}

Research only; validate prospectively before changing production gates.
