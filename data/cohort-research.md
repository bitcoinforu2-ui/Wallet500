# Wallet500 Cohort Research

Generated: 2026-09-14T05:25:47.343149+00:00
Source snapshot: 2026-09-14T05:19:29.322477+00:00

## Baseline
- N=359 ROI=-0.8088% P/L=$-2.90371

## Best post-hoc counterfactuals (min 5 retained)
- liq>=250k: N=128 ROI=-0.3864% delta=0.4224pp
- liq>=500k: N=174 ROI=-0.4421% delta=0.3667pp
- turnover<=1: N=193 ROI=-0.498% delta=0.3108pp
- vol>=50k: N=359 ROI=-0.8088% delta=0.0pp
- turnover<=2: N=285 ROI=-0.8126% delta=-0.0038pp
- liq>=100k: N=232 ROI=-0.8452% delta=-0.0364pp
- liq>=100k & vol>=50k: N=232 ROI=-0.8452% delta=-0.0364pp
- tx>=100: N=328 ROI=-0.9136% delta=-0.1048pp
- vol>=25k: N=330 ROI=-0.934% delta=-0.1252pp
- liq>=75k: N=286 ROI=-1.0353% delta=-0.2265pp

## Missed-star scan
- Candidates: 1165
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 71, 'LIQ_LT_15K': 1047, 'VOL_LT_15K': 723, 'TX_LT_50': 588}

Research only; validate prospectively before changing production gates.
