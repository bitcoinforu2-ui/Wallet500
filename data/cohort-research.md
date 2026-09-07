# Wallet500 Cohort Research

Generated: 2026-09-07T03:05:03.597207+00:00
Source snapshot: 2026-09-07T02:57:10.028920+00:00

## Baseline
- N=355 ROI=-0.7617% P/L=$-2.704119

## Best post-hoc counterfactuals (min 5 retained)
- liq>=250k: N=128 ROI=-0.3864% delta=0.3753pp
- turnover<=1: N=192 ROI=-0.3967% delta=0.365pp
- turnover<=2: N=281 ROI=-0.7532% delta=0.0085pp
- liq>=100k: N=232 ROI=-0.7592% delta=0.0025pp
- tx>=100: N=325 ROI=-0.8607% delta=-0.099pp
- vol>=25k: N=328 ROI=-0.8788% delta=-0.1171pp
- liq>=75k: N=286 ROI=-0.9655% delta=-0.2038pp
- tx>=500: N=183 ROI=-1.0056% delta=-0.2439pp
- tx>=250: N=282 ROI=-1.0071% delta=-0.2454pp
- liq>=100k & tx>=250: N=182 ROI=-1.0425% delta=-0.2808pp

## Missed-star scan
- Candidates: 1165
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 76, 'LIQ_LT_50K': 1042, 'VOL_LT_15K': 718, 'TX_LT_50': 580}

Research only; validate prospectively before changing production gates.
