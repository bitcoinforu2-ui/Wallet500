# Wallet500 Cohort Research

Generated: 2026-09-04T12:36:57.137268+00:00
Source snapshot: 2026-09-04T12:29:52.721936+00:00

## Baseline
- N=355 ROI=-0.7276% P/L=$-2.582894

## Best post-hoc counterfactuals (min 5 retained)
- turnover<=1: N=192 ROI=-0.3335% delta=0.3941pp
- liq>=250k: N=128 ROI=-0.3864% delta=0.3412pp
- liq>=100k: N=232 ROI=-0.7069% delta=0.0207pp
- turnover<=2: N=281 ROI=-0.71% delta=0.0176pp
- tx>=100: N=325 ROI=-0.8234% delta=-0.0958pp
- vol>=25k: N=328 ROI=-0.8419% delta=-0.1143pp
- liq>=75k: N=286 ROI=-0.9231% delta=-0.1955pp
- tx>=500: N=183 ROI=-0.9393% delta=-0.2117pp
- tx>=250: N=282 ROI=-0.9641% delta=-0.2365pp
- liq>=100k & tx>=250: N=182 ROI=-0.9759% delta=-0.2483pp

## Missed-star scan
- Candidates: 1165
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 76, 'LIQ_LT_50K': 1042, 'VOL_LT_15K': 718, 'TX_LT_50': 580}

Research only; validate prospectively before changing production gates.
