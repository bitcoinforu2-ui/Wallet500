# Wallet500 Cohort Research

Generated: 2026-09-05T00:45:30.666743+00:00
Source snapshot: 2026-09-05T00:38:07.808598+00:00

## Baseline
- N=355 ROI=-0.7262% P/L=$-2.577996

## Best post-hoc counterfactuals (min 5 retained)
- turnover<=1: N=192 ROI=-0.331% delta=0.3952pp
- liq>=250k: N=128 ROI=-0.3864% delta=0.3398pp
- liq>=100k: N=232 ROI=-0.7048% delta=0.0214pp
- turnover<=2: N=281 ROI=-0.7083% delta=0.0179pp
- tx>=100: N=325 ROI=-0.8218% delta=-0.0956pp
- vol>=25k: N=328 ROI=-0.8404% delta=-0.1142pp
- liq>=75k: N=286 ROI=-0.9214% delta=-0.1952pp
- tx>=500: N=183 ROI=-0.9367% delta=-0.2105pp
- tx>=250: N=282 ROI=-0.9624% delta=-0.2362pp
- liq>=100k & tx>=250: N=182 ROI=-0.9732% delta=-0.247pp

## Missed-star scan
- Candidates: 1165
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 76, 'LIQ_LT_50K': 1042, 'VOL_LT_15K': 718, 'TX_LT_50': 580}

Research only; validate prospectively before changing production gates.
