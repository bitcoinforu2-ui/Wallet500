# Wallet500 Cohort Research

Generated: 2026-08-31T04:06:33.462466+00:00
Source snapshot: 2026-08-31T04:06:32.041447+00:00

## Baseline
- N=81 ROI=-21.1444% P/L=$-17.126935

## Best post-hoc counterfactuals (min 5 retained)
- liq>=250k & vol>=100k: N=33 ROI=-3.1017% delta=18.0427pp
- liq>=250k: N=42 ROI=-3.755% delta=17.3894pp
- liq>=500k: N=29 ROI=-4.9476% delta=16.1968pp
- liq>=100k: N=60 ROI=-8.9527% delta=12.1917pp
- liq>=100k & vol>=50k: N=53 ROI=-9.4622% delta=11.6822pp
- turnover<=1: N=54 ROI=-9.7093% delta=11.4351pp
- liq>=100k & tx>=250: N=41 ROI=-10.4505% delta=10.6939pp
- liq>=75k: N=70 ROI=-17.9577% delta=3.1867pp
- tx>=500: N=36 ROI=-18.3162% delta=2.8282pp
- vol>=100k: N=49 ROI=-18.4351% delta=2.7093pp

## Missed-star scan
- Candidates: 464
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 34, 'LIQ_LT_50K': 410, 'VOL_LT_15K': 300, 'TX_LT_50': 250}

Research only; validate prospectively before changing production gates.
