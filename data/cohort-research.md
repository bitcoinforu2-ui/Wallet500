# Wallet500 Cohort Research

Generated: 2026-09-07T05:01:57.924358+00:00
Source snapshot: 2026-09-07T04:54:21.881991+00:00

## Baseline
- N=355 ROI=-0.7618% P/L=$-2.704527

## Best post-hoc counterfactuals (min 5 retained)
- liq>=250k: N=128 ROI=-0.3864% delta=0.3754pp
- turnover<=1: N=192 ROI=-0.3969% delta=0.3649pp
- turnover<=2: N=281 ROI=-0.7533% delta=0.0085pp
- liq>=100k: N=232 ROI=-0.7594% delta=0.0024pp
- tx>=100: N=325 ROI=-0.8608% delta=-0.099pp
- vol>=25k: N=328 ROI=-0.879% delta=-0.1172pp
- liq>=75k: N=286 ROI=-0.9656% delta=-0.2038pp
- tx>=500: N=183 ROI=-1.0058% delta=-0.244pp
- tx>=250: N=282 ROI=-1.0073% delta=-0.2455pp
- liq>=100k & tx>=250: N=182 ROI=-1.0427% delta=-0.2809pp

## Missed-star scan
- Candidates: 1165
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 76, 'LIQ_LT_50K': 1042, 'VOL_LT_15K': 718, 'TX_LT_50': 580}

Research only; validate prospectively before changing production gates.
