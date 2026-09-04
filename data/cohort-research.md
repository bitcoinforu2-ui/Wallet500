# Wallet500 Cohort Research

Generated: 2026-09-04T10:15:32.821806+00:00
Source snapshot: 2026-09-04T10:07:59.413749+00:00

## Baseline
- N=355 ROI=-0.7253% P/L=$-2.574731

## Best post-hoc counterfactuals (min 5 retained)
- turnover<=1: N=192 ROI=-0.3293% delta=0.396pp
- liq>=250k: N=128 ROI=-0.3864% delta=0.3389pp
- liq>=100k: N=232 ROI=-0.7034% delta=0.0219pp
- turnover<=2: N=281 ROI=-0.7071% delta=0.0182pp
- tx>=100: N=325 ROI=-0.8208% delta=-0.0955pp
- vol>=25k: N=328 ROI=-0.8394% delta=-0.1141pp
- liq>=75k: N=286 ROI=-0.9202% delta=-0.1949pp
- tx>=500: N=183 ROI=-0.9349% delta=-0.2096pp
- tx>=250: N=282 ROI=-0.9612% delta=-0.2359pp
- liq>=100k & tx>=250: N=182 ROI=-0.9714% delta=-0.2461pp

## Missed-star scan
- Candidates: 1165
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 76, 'LIQ_LT_50K': 1042, 'VOL_LT_15K': 718, 'TX_LT_50': 580}

Research only; validate prospectively before changing production gates.
