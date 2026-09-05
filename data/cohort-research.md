# Wallet500 Cohort Research

Generated: 2026-09-05T04:16:33.004400+00:00
Source snapshot: 2026-09-05T04:08:23.155479+00:00

## Baseline
- N=355 ROI=-0.723% P/L=$-2.566568

## Best post-hoc counterfactuals (min 5 retained)
- turnover<=1: N=192 ROI=-0.325% delta=0.398pp
- liq>=250k: N=128 ROI=-0.3864% delta=0.3366pp
- liq>=100k: N=232 ROI=-0.6999% delta=0.0231pp
- turnover<=2: N=281 ROI=-0.7042% delta=0.0188pp
- tx>=100: N=325 ROI=-0.8183% delta=-0.0953pp
- vol>=25k: N=328 ROI=-0.8369% delta=-0.1139pp
- liq>=75k: N=286 ROI=-0.9174% delta=-0.1944pp
- tx>=500: N=183 ROI=-0.9304% delta=-0.2074pp
- tx>=250: N=282 ROI=-0.9584% delta=-0.2354pp
- liq>=100k & tx>=250: N=182 ROI=-0.9669% delta=-0.2439pp

## Missed-star scan
- Candidates: 1165
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 76, 'LIQ_LT_50K': 1042, 'VOL_LT_15K': 718, 'TX_LT_50': 580}

Research only; validate prospectively before changing production gates.
