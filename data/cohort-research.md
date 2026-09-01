# Wallet500 Cohort Research

Generated: 2026-09-01T04:40:36.561057+00:00
Source snapshot: 2026-09-01T04:40:34.437172+00:00

## Baseline
- N=193 ROI=-13.095% P/L=$-25.273315

## Best post-hoc counterfactuals (min 5 retained)
- liq>=250k & vol>=100k: N=67 ROI=22.6888% delta=35.7838pp
- liq>=250k: N=88 ROI=17.6476% delta=30.7426pp
- tx>=500: N=89 ROI=4.7523% delta=17.8473pp
- liq>=100k & tx>=250: N=103 ROI=3.8253% delta=16.9203pp
- liq>=100k & vol>=50k: N=113 ROI=2.7135% delta=15.8085pp
- liq>=100k: N=138 ROI=2.3892% delta=15.4842pp
- liq>=500k: N=52 ROI=-5.7197% delta=7.3753pp
- turnover<=1: N=112 ROI=-5.9491% delta=7.1459pp
- liq>=75k: N=163 ROI=-8.5793% delta=4.5157pp
- vol>=100k: N=114 ROI=-10.0598% delta=3.0352pp

## Missed-star scan
- Candidates: 752
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 49, 'LIQ_LT_50K': 668, 'VOL_LT_15K': 466, 'TX_LT_50': 374}

Research only; validate prospectively before changing production gates.
