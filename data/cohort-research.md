# Wallet500 Cohort Research

Generated: 2026-08-31T12:06:10.122909+00:00
Source snapshot: 2026-08-31T12:06:08.838261+00:00

## Baseline
- N=122 ROI=-22.1198% P/L=$-26.986121

## Best post-hoc counterfactuals (min 5 retained)
- liq>=250k: N=54 ROI=-4.0734% delta=18.0464pp
- liq>=250k & vol>=100k: N=43 ROI=-4.4918% delta=17.628pp
- turnover<=1: N=73 ROI=-5.9744% delta=16.1454pp
- liq>=500k: N=34 ROI=-6.4232% delta=15.6966pp
- liq>=100k: N=87 ROI=-10.0988% delta=12.021pp
- liq>=100k & vol>=50k: N=73 ROI=-11.655% delta=10.4648pp
- liq>=100k & tx>=250: N=64 ROI=-12.584% delta=9.5358pp
- tx>=500: N=54 ROI=-16.5716% delta=5.5482pp
- liq>=75k: N=102 ROI=-18.458% delta=3.6618pp
- turnover<=2: N=99 ROI=-22.7115% delta=-0.5917pp

## Missed-star scan
- Candidates: 573
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 41, 'LIQ_LT_50K': 507, 'VOL_LT_15K': 365, 'TX_LT_50': 301}

Research only; validate prospectively before changing production gates.
