# Wallet500 Cohort Research

Generated: 2026-09-01T09:10:33.170486+00:00
Source snapshot: 2026-09-01T09:10:30.789432+00:00

## Baseline
- N=234 ROI=-17.1536% P/L=$-40.139323

## Best post-hoc counterfactuals (min 5 retained)
- liq>=250k & vol>=100k: N=79 ROI=17.6998% delta=34.8534pp
- liq>=250k: N=101 ROI=14.5615% delta=31.7151pp
- tx>=500: N=109 ROI=1.0032% delta=18.1568pp
- liq>=100k & tx>=250: N=124 ROI=-0.2295% delta=16.9241pp
- liq>=100k: N=165 ROI=-1.5902% delta=15.5634pp
- liq>=100k & vol>=50k: N=136 ROI=-1.8917% delta=15.2619pp
- liq>=500k: N=59 ROI=-6.4604% delta=10.6932pp
- turnover<=1: N=135 ROI=-8.2636% delta=8.89pp
- liq>=75k: N=196 ROI=-13.1769% delta=3.9767pp
- vol>=100k: N=138 ROI=-15.7812% delta=1.3724pp

## Missed-star scan
- Candidates: 842
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 54, 'LIQ_LT_50K': 752, 'VOL_LT_15K': 529, 'TX_LT_50': 422}

Research only; validate prospectively before changing production gates.
