# Wallet500 Cohort Research

Generated: 2026-09-24T07:09:54.654413+00:00
Source snapshot: 2026-09-24T07:03:28.705164+00:00

## Baseline
- N=359 ROI=-0.7577% P/L=$-2.720037

## Best post-hoc counterfactuals (min 5 retained)
- liq>=250k: N=128 ROI=-0.3864% delta=0.3713pp
- turnover<=1: N=193 ROI=-0.4029% delta=0.3548pp
- liq>=500k: N=174 ROI=-0.4421% delta=0.3156pp
- turnover<=2: N=285 ROI=-0.7482% delta=0.0095pp
- vol>=50k: N=359 ROI=-0.7577% delta=0.0pp
- liq>=100k: N=232 ROI=-0.7661% delta=-0.0084pp
- liq>=100k & vol>=50k: N=232 ROI=-0.7661% delta=-0.0084pp
- tx>=100: N=328 ROI=-0.8576% delta=-0.0999pp
- vol>=25k: N=330 ROI=-0.8783% delta=-0.1206pp
- liq>=75k: N=286 ROI=-0.971% delta=-0.2133pp

## Missed-star scan
- Candidates: 1165
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 71, 'LIQ_LT_15K': 1047, 'VOL_LT_15K': 723, 'TX_LT_50': 588}

Research only; validate prospectively before changing production gates.
