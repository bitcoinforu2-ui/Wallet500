# Wallet500 Cohort Research

Generated: 2026-08-31T05:49:39.331809+00:00
Source snapshot: 2026-08-31T05:49:37.885942+00:00

## Baseline
- N=93 ROI=-23.6587% P/L=$-22.002614

## Best post-hoc counterfactuals (min 5 retained)
- liq>=250k & vol>=100k: N=35 ROI=-3.6565% delta=20.0022pp
- liq>=250k: N=46 ROI=-3.9626% delta=19.6961pp
- liq>=500k: N=30 ROI=-5.3836% delta=18.2751pp
- turnover<=1: N=59 ROI=-9.1012% delta=14.5575pp
- liq>=100k: N=68 ROI=-10.934% delta=12.7247pp
- liq>=100k & vol>=50k: N=57 ROI=-12.1468% delta=11.5119pp
- liq>=100k & tx>=250: N=48 ROI=-13.0996% delta=10.5591pp
- tx>=500: N=38 ROI=-17.2073% delta=6.4514pp
- liq>=75k: N=79 ROI=-19.6411% delta=4.0176pp
- vol>=100k: N=55 ROI=-23.4227% delta=0.236pp

## Missed-star scan
- Candidates: 487
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 36, 'LIQ_LT_50K': 429, 'VOL_LT_15K': 314, 'TX_LT_50': 264}

Research only; validate prospectively before changing production gates.
