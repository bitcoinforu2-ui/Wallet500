# Wallet500 Cohort Research

Generated: 2026-09-01T05:40:54.382197+00:00
Source snapshot: 2026-09-01T05:40:52.242165+00:00

## Baseline
- N=203 ROI=-13.206% P/L=$-26.80809

## Best post-hoc counterfactuals (min 5 retained)
- liq>=250k & vol>=100k: N=71 ROI=21.6987% delta=34.9047pp
- liq>=250k: N=92 ROI=17.3462% delta=30.5522pp
- tx>=500: N=93 ROI=5.2532% delta=18.4592pp
- liq>=100k & tx>=250: N=108 ROI=4.2188% delta=17.4248pp
- liq>=100k & vol>=50k: N=118 ROI=3.0144% delta=16.2204pp
- liq>=100k: N=144 ROI=2.709% delta=15.915pp
- liq>=500k: N=54 ROI=-4.7389% delta=8.4671pp
- turnover<=1: N=118 ROI=-5.5631% delta=7.6429pp
- liq>=75k: N=171 ROI=-8.4398% delta=4.7662pp
- vol>=100k: N=121 ROI=-10.6605% delta=2.5455pp

## Missed-star scan
- Candidates: 768
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 50, 'LIQ_LT_50K': 684, 'VOL_LT_15K': 478, 'TX_LT_50': 382}

Research only; validate prospectively before changing production gates.
