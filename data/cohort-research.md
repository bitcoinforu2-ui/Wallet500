# Wallet500 Cohort Research

Generated: 2026-09-19T13:36:36.234530+00:00
Source snapshot: 2026-09-19T13:30:30.283380+00:00

## Baseline
- N=359 ROI=-0.7024% P/L=$-2.52167

## Best post-hoc counterfactuals (min 5 retained)
- turnover<=1: N=193 ROI=-0.3001% delta=0.4023pp
- liq>=250k: N=128 ROI=-0.3864% delta=0.316pp
- liq>=500k: N=174 ROI=-0.4421% delta=0.2603pp
- turnover<=2: N=285 ROI=-0.6786% delta=0.0238pp
- liq>=100k: N=232 ROI=-0.6806% delta=0.0218pp
- liq>=100k & vol>=50k: N=232 ROI=-0.6806% delta=0.0218pp
- vol>=50k: N=359 ROI=-0.7024% delta=0.0pp
- tx>=100: N=328 ROI=-0.7972% delta=-0.0948pp
- vol>=25k: N=330 ROI=-0.8182% delta=-0.1158pp
- tx>=500: N=184 ROI=-0.901% delta=-0.1986pp

## Missed-star scan
- Candidates: 1165
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 71, 'LIQ_LT_15K': 1047, 'VOL_LT_15K': 723, 'TX_LT_50': 588}

Research only; validate prospectively before changing production gates.
