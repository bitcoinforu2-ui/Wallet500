# Wallet500 Cohort Research

Generated: 2026-09-19T09:04:12.322339+00:00
Source snapshot: 2026-09-19T08:57:42.944605+00:00

## Baseline
- N=359 ROI=-0.6866% P/L=$-2.464935

## Best post-hoc counterfactuals (min 5 retained)
- turnover<=1: N=193 ROI=-0.2707% delta=0.4159pp
- liq>=250k: N=128 ROI=-0.3864% delta=0.3002pp
- liq>=500k: N=174 ROI=-0.4421% delta=0.2445pp
- liq>=100k: N=232 ROI=-0.6561% delta=0.0305pp
- liq>=100k & vol>=50k: N=232 ROI=-0.6561% delta=0.0305pp
- turnover<=2: N=285 ROI=-0.6587% delta=0.0279pp
- vol>=50k: N=359 ROI=-0.6866% delta=0.0pp
- tx>=100: N=328 ROI=-0.7799% delta=-0.0933pp
- vol>=25k: N=330 ROI=-0.801% delta=-0.1144pp
- tx>=500: N=184 ROI=-0.8701% delta=-0.1835pp

## Missed-star scan
- Candidates: 1165
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 71, 'LIQ_LT_15K': 1047, 'VOL_LT_15K': 723, 'TX_LT_50': 588}

Research only; validate prospectively before changing production gates.
