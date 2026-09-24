# Wallet500 Cohort Research

Generated: 2026-09-24T06:32:39.998580+00:00
Source snapshot: 2026-09-24T06:26:12.375999+00:00

## Baseline
- N=359 ROI=-0.7576% P/L=$-2.719629

## Best post-hoc counterfactuals (min 5 retained)
- liq>=250k: N=128 ROI=-0.3864% delta=0.3712pp
- turnover<=1: N=193 ROI=-0.4026% delta=0.355pp
- liq>=500k: N=174 ROI=-0.4421% delta=0.3155pp
- turnover<=2: N=285 ROI=-0.748% delta=0.0096pp
- vol>=50k: N=359 ROI=-0.7576% delta=0.0pp
- liq>=100k: N=232 ROI=-0.7659% delta=-0.0083pp
- liq>=100k & vol>=50k: N=232 ROI=-0.7659% delta=-0.0083pp
- tx>=100: N=328 ROI=-0.8575% delta=-0.0999pp
- vol>=25k: N=330 ROI=-0.8782% delta=-0.1206pp
- liq>=75k: N=286 ROI=-0.9709% delta=-0.2133pp

## Missed-star scan
- Candidates: 1165
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 71, 'LIQ_LT_15K': 1047, 'VOL_LT_15K': 723, 'TX_LT_50': 588}

Research only; validate prospectively before changing production gates.
