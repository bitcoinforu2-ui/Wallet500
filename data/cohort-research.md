# Wallet500 Cohort Research

Generated: 2026-10-05T23:03:46.863031+00:00
Source snapshot: 2026-10-05T22:57:01.157142+00:00

## Baseline
- N=359 ROI=-0.8043% P/L=$-2.887384

## Best post-hoc counterfactuals (min 5 retained)
- liq>=250k: N=128 ROI=-0.3864% delta=0.4179pp
- liq>=500k: N=174 ROI=-0.4421% delta=0.3622pp
- turnover<=1: N=193 ROI=-0.4896% delta=0.3147pp
- vol>=50k: N=359 ROI=-0.8043% delta=0.0pp
- turnover<=2: N=285 ROI=-0.8069% delta=-0.0026pp
- liq>=100k: N=232 ROI=-0.8382% delta=-0.0339pp
- liq>=100k & vol>=50k: N=232 ROI=-0.8382% delta=-0.0339pp
- tx>=100: N=328 ROI=-0.9087% delta=-0.1044pp
- vol>=25k: N=330 ROI=-0.9291% delta=-0.1248pp
- liq>=75k: N=286 ROI=-1.0295% delta=-0.2252pp

## Missed-star scan
- Candidates: 1165
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 71, 'LIQ_LT_15K': 1047, 'VOL_LT_15K': 723, 'TX_LT_50': 588}

Research only; validate prospectively before changing production gates.
