# Wallet500 Cohort Research

Generated: 2026-09-01T04:07:30.647612+00:00
Source snapshot: 2026-09-01T04:07:29.188234+00:00

## Baseline
- N=192 ROI=-18.1967% P/L=$-34.937637

## Best post-hoc counterfactuals (min 5 retained)
- liq>=250k & vol>=100k: N=67 ROI=8.6654% delta=26.8621pp
- liq>=250k: N=88 ROI=6.8159% delta=25.0126pp
- liq>=100k: N=137 ROI=-4.8421% delta=13.3546pp
- liq>=100k & tx>=250: N=102 ROI=-5.4067% delta=12.79pp
- liq>=500k: N=52 ROI=-5.5423% delta=12.6544pp
- tx>=500: N=88 ROI=-5.806% delta=12.3907pp
- liq>=100k & vol>=50k: N=112 ROI=-6.0581% delta=12.1386pp
- turnover<=1: N=111 ROI=-6.2877% delta=11.909pp
- liq>=75k: N=162 ROI=-14.7743% delta=3.4224pp
- vol>=100k: N=114 ROI=-18.3119% delta=-0.1152pp

## Missed-star scan
- Candidates: 744
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 47, 'LIQ_LT_50K': 662, 'VOL_LT_15K': 462, 'TX_LT_50': 373}

Research only; validate prospectively before changing production gates.
