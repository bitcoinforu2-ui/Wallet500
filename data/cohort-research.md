# Wallet500 Cohort Research

Generated: 2026-09-07T00:59:10.723894+00:00
Source snapshot: 2026-09-07T00:51:12.925464+00:00

## Baseline
- N=355 ROI=-0.7217% P/L=$-2.562078

## Best post-hoc counterfactuals (min 5 retained)
- turnover<=1: N=192 ROI=-0.3227% delta=0.399pp
- liq>=250k: N=128 ROI=-0.3864% delta=0.3353pp
- liq>=100k: N=232 ROI=-0.698% delta=0.0237pp
- turnover<=2: N=281 ROI=-0.7026% delta=0.0191pp
- tx>=100: N=325 ROI=-0.8169% delta=-0.0952pp
- vol>=25k: N=328 ROI=-0.8355% delta=-0.1138pp
- liq>=75k: N=286 ROI=-0.9158% delta=-0.1941pp
- tx>=500: N=183 ROI=-0.928% delta=-0.2063pp
- tx>=250: N=282 ROI=-0.9568% delta=-0.2351pp
- liq>=100k & tx>=250: N=182 ROI=-0.9644% delta=-0.2427pp

## Missed-star scan
- Candidates: 1165
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 76, 'LIQ_LT_50K': 1042, 'VOL_LT_15K': 718, 'TX_LT_50': 580}

Research only; validate prospectively before changing production gates.
