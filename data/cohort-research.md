# Wallet500 Cohort Research

Generated: 2026-09-19T17:50:22.166089+00:00
Source snapshot: 2026-09-19T17:43:57.609996+00:00

## Baseline
- N=359 ROI=-0.722% P/L=$-2.591874

## Best post-hoc counterfactuals (min 5 retained)
- turnover<=1: N=193 ROI=-0.3365% delta=0.3855pp
- liq>=250k: N=128 ROI=-0.3864% delta=0.3356pp
- liq>=500k: N=174 ROI=-0.4421% delta=0.2799pp
- turnover<=2: N=285 ROI=-0.7032% delta=0.0188pp
- liq>=100k: N=232 ROI=-0.7108% delta=0.0112pp
- liq>=100k & vol>=50k: N=232 ROI=-0.7108% delta=0.0112pp
- vol>=50k: N=359 ROI=-0.722% delta=0.0pp
- tx>=100: N=328 ROI=-0.8186% delta=-0.0966pp
- vol>=25k: N=330 ROI=-0.8395% delta=-0.1175pp
- liq>=75k: N=286 ROI=-0.9262% delta=-0.2042pp

## Missed-star scan
- Candidates: 1165
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 71, 'LIQ_LT_15K': 1047, 'VOL_LT_15K': 723, 'TX_LT_50': 588}

Research only; validate prospectively before changing production gates.
