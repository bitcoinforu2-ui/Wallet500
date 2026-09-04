# Wallet500 Cohort Research

Generated: 2026-09-04T18:18:55.041057+00:00
Source snapshot: 2026-09-04T18:11:25.415949+00:00

## Baseline
- N=355 ROI=-0.7279% P/L=$-2.584119

## Best post-hoc counterfactuals (min 5 retained)
- turnover<=1: N=192 ROI=-0.3342% delta=0.3937pp
- liq>=250k: N=128 ROI=-0.3864% delta=0.3415pp
- liq>=100k: N=232 ROI=-0.7075% delta=0.0204pp
- turnover<=2: N=281 ROI=-0.7104% delta=0.0175pp
- tx>=100: N=325 ROI=-0.8237% delta=-0.0958pp
- vol>=25k: N=328 ROI=-0.8423% delta=-0.1144pp
- liq>=75k: N=286 ROI=-0.9235% delta=-0.1956pp
- tx>=500: N=183 ROI=-0.94% delta=-0.2121pp
- tx>=250: N=282 ROI=-0.9646% delta=-0.2367pp
- liq>=100k & tx>=250: N=182 ROI=-0.9765% delta=-0.2486pp

## Missed-star scan
- Candidates: 1165
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 76, 'LIQ_LT_50K': 1042, 'VOL_LT_15K': 718, 'TX_LT_50': 580}

Research only; validate prospectively before changing production gates.
