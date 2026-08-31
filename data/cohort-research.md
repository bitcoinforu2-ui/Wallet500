# Wallet500 Cohort Research

Generated: 2026-08-31T02:35:58.330286+00:00
Source snapshot: 2026-08-31T02:35:56.999691+00:00

## Baseline
- N=75 ROI=-18.858% P/L=$-14.143471

## Best post-hoc counterfactuals (min 5 retained)
- liq>=250k & vol>=100k: N=32 ROI=-4.4503% delta=14.4077pp
- liq>=250k: N=41 ROI=-4.694% delta=14.164pp
- liq>=500k: N=28 ROI=-6.3067% delta=12.5513pp
- turnover<=1: N=52 ROI=-8.8003% delta=10.0577pp
- liq>=100k: N=57 ROI=-9.4726% delta=9.3854pp
- liq>=100k & vol>=50k: N=50 ROI=-10.0828% delta=8.7752pp
- liq>=100k & tx>=250: N=38 ROI=-10.4602% delta=8.3978pp
- liq>=75k: N=64 ROI=-14.9469% delta=3.9111pp
- vol>=100k: N=45 ROI=-15.2931% delta=3.5649pp
- turnover<=2: N=64 ROI=-17.3658% delta=1.4922pp

## Missed-star scan
- Candidates: 446
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 31, 'LIQ_LT_50K': 396, 'VOL_LT_15K': 295, 'TX_LT_50': 246}

Research only; validate prospectively before changing production gates.
