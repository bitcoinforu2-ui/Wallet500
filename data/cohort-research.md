# Wallet500 Cohort Research

Generated: 2026-08-31T04:19:56.918646+00:00
Source snapshot: 2026-08-31T04:19:55.407451+00:00

## Baseline
- N=82 ROI=-20.8121% P/L=$-17.06594

## Best post-hoc counterfactuals (min 5 retained)
- liq>=250k & vol>=100k: N=33 ROI=-2.8801% delta=17.932pp
- liq>=250k: N=42 ROI=-3.4829% delta=17.3292pp
- liq>=500k: N=29 ROI=-4.5608% delta=16.2513pp
- liq>=100k: N=60 ROI=-8.994% delta=11.8181pp
- liq>=100k & vol>=50k: N=53 ROI=-9.4066% delta=11.4055pp
- turnover<=1: N=54 ROI=-9.5778% delta=11.2343pp
- liq>=100k & tx>=250: N=41 ROI=-10.4663% delta=10.3458pp
- liq>=75k: N=71 ROI=-17.5711% delta=3.241pp
- vol>=100k: N=50 ROI=-18.1766% delta=2.6355pp
- tx>=500: N=36 ROI=-18.4278% delta=2.3843pp

## Missed-star scan
- Candidates: 470
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 34, 'LIQ_LT_50K': 416, 'VOL_LT_15K': 304, 'TX_LT_50': 257}

Research only; validate prospectively before changing production gates.
