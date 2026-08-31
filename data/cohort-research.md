# Wallet500 Cohort Research

Generated: 2026-08-31T23:05:31.340103+00:00
Source snapshot: 2026-08-31T23:05:29.335975+00:00

## Baseline
- N=165 ROI=-18.9048% P/L=$-31.192848

## Best post-hoc counterfactuals (min 5 retained)
- liq>=250k & vol>=100k: N=55 ROI=5.2532% delta=24.158pp
- liq>=250k: N=72 ROI=4.9444% delta=23.8492pp
- liq>=500k: N=41 ROI=-3.8952% delta=15.0096pp
- turnover<=1: N=96 ROI=-6.665% delta=12.2398pp
- liq>=100k: N=120 ROI=-7.3268% delta=11.578pp
- liq>=100k & tx>=250: N=89 ROI=-8.3579% delta=10.5469pp
- tx>=500: N=76 ROI=-9.2223% delta=9.6825pp
- liq>=100k & vol>=50k: N=99 ROI=-9.2813% delta=9.6235pp
- liq>=75k: N=139 ROI=-15.6039% delta=3.3009pp
- vol>=25k: N=152 ROI=-20.6897% delta=-1.7849pp

## Missed-star scan
- Candidates: 681
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 45, 'LIQ_LT_50K': 605, 'VOL_LT_15K': 432, 'TX_LT_50': 351}

Research only; validate prospectively before changing production gates.
