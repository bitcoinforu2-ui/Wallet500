# Wallet500 Cohort Research

Generated: 2026-08-31T11:11:05.351009+00:00
Source snapshot: 2026-08-31T11:11:03.676369+00:00

## Baseline
- N=121 ROI=-21.8918% P/L=$-26.489135

## Best post-hoc counterfactuals (min 5 retained)
- liq>=250k: N=54 ROI=-3.9691% delta=17.9227pp
- liq>=250k & vol>=100k: N=43 ROI=-4.3996% delta=17.4922pp
- turnover<=1: N=73 ROI=-5.6637% delta=16.2281pp
- liq>=500k: N=34 ROI=-6.2581% delta=15.6337pp
- liq>=100k: N=86 ROI=-9.6409% delta=12.2509pp
- liq>=100k & vol>=50k: N=72 ROI=-11.0172% delta=10.8746pp
- liq>=100k & tx>=250: N=63 ROI=-12.3126% delta=9.5792pp
- tx>=500: N=53 ROI=-16.3205% delta=5.5713pp
- liq>=75k: N=101 ROI=-18.1508% delta=3.741pp
- turnover<=2: N=99 ROI=-22.4702% delta=-0.5784pp

## Missed-star scan
- Candidates: 564
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 44, 'LIQ_LT_50K': 496, 'VOL_LT_15K': 356, 'TX_LT_50': 296}

Research only; validate prospectively before changing production gates.
