# Wallet500 Cohort Research

Generated: 2026-09-07T02:08:30.014314+00:00
Source snapshot: 2026-09-07T02:00:53.814444+00:00

## Baseline
- N=355 ROI=-0.7652% P/L=$-2.716364

## Best post-hoc counterfactuals (min 5 retained)
- liq>=250k: N=128 ROI=-0.3864% delta=0.3788pp
- turnover<=1: N=192 ROI=-0.403% delta=0.3622pp
- turnover<=2: N=281 ROI=-0.7575% delta=0.0077pp
- liq>=100k: N=232 ROI=-0.7645% delta=0.0007pp
- tx>=100: N=325 ROI=-0.8644% delta=-0.0992pp
- vol>=25k: N=328 ROI=-0.8826% delta=-0.1174pp
- liq>=75k: N=286 ROI=-0.9697% delta=-0.2045pp
- tx>=250: N=282 ROI=-1.0115% delta=-0.2463pp
- tx>=500: N=183 ROI=-1.0123% delta=-0.2471pp
- liq>=100k & tx>=250: N=182 ROI=-1.0492% delta=-0.284pp

## Missed-star scan
- Candidates: 1165
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 76, 'LIQ_LT_50K': 1042, 'VOL_LT_15K': 718, 'TX_LT_50': 580}

Research only; validate prospectively before changing production gates.
