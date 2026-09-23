# Wallet500 Cohort Research

Generated: 2026-09-23T08:29:34.625569+00:00
Source snapshot: 2026-09-23T08:22:45.829023+00:00

## Baseline
- N=359 ROI=-0.7495% P/L=$-2.690649

## Best post-hoc counterfactuals (min 5 retained)
- liq>=250k: N=128 ROI=-0.3864% delta=0.3631pp
- turnover<=1: N=193 ROI=-0.3876% delta=0.3619pp
- liq>=500k: N=174 ROI=-0.4421% delta=0.3074pp
- turnover<=2: N=285 ROI=-0.7379% delta=0.0116pp
- vol>=50k: N=359 ROI=-0.7495% delta=0.0pp
- liq>=100k: N=232 ROI=-0.7534% delta=-0.0039pp
- liq>=100k & vol>=50k: N=232 ROI=-0.7534% delta=-0.0039pp
- tx>=100: N=328 ROI=-0.8487% delta=-0.0992pp
- vol>=25k: N=330 ROI=-0.8694% delta=-0.1199pp
- liq>=75k: N=286 ROI=-0.9608% delta=-0.2113pp

## Missed-star scan
- Candidates: 1165
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 71, 'LIQ_LT_15K': 1047, 'VOL_LT_15K': 723, 'TX_LT_50': 588}

Research only; validate prospectively before changing production gates.
