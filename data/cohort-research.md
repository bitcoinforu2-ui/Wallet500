# Wallet500 Cohort Research

Generated: 2026-09-07T06:33:21.949166+00:00
Source snapshot: 2026-09-07T06:25:23.836300+00:00

## Baseline
- N=355 ROI=-0.7601% P/L=$-2.698404

## Best post-hoc counterfactuals (min 5 retained)
- liq>=250k: N=128 ROI=-0.3864% delta=0.3737pp
- turnover<=1: N=192 ROI=-0.3937% delta=0.3664pp
- turnover<=2: N=281 ROI=-0.7511% delta=0.009pp
- liq>=100k: N=232 ROI=-0.7567% delta=0.0034pp
- tx>=100: N=325 ROI=-0.8589% delta=-0.0988pp
- vol>=25k: N=328 ROI=-0.8771% delta=-0.117pp
- liq>=75k: N=286 ROI=-0.9635% delta=-0.2034pp
- tx>=500: N=183 ROI=-1.0025% delta=-0.2424pp
- tx>=250: N=282 ROI=-1.0051% delta=-0.245pp
- liq>=100k & tx>=250: N=182 ROI=-1.0393% delta=-0.2792pp

## Missed-star scan
- Candidates: 1165
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 76, 'LIQ_LT_50K': 1042, 'VOL_LT_15K': 718, 'TX_LT_50': 580}

Research only; validate prospectively before changing production gates.
