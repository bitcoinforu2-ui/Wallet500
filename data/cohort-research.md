# Wallet500 Cohort Research

Generated: 2026-09-24T10:28:25.388593+00:00
Source snapshot: 2026-09-24T10:21:49.577253+00:00

## Baseline
- N=359 ROI=-0.7664% P/L=$-2.751466

## Best post-hoc counterfactuals (min 5 retained)
- liq>=250k: N=128 ROI=-0.3864% delta=0.38pp
- turnover<=1: N=193 ROI=-0.4191% delta=0.3473pp
- liq>=500k: N=174 ROI=-0.4421% delta=0.3243pp
- turnover<=2: N=285 ROI=-0.7592% delta=0.0072pp
- vol>=50k: N=359 ROI=-0.7664% delta=0.0pp
- liq>=100k: N=232 ROI=-0.7796% delta=-0.0132pp
- liq>=100k & vol>=50k: N=232 ROI=-0.7796% delta=-0.0132pp
- tx>=100: N=328 ROI=-0.8672% delta=-0.1008pp
- vol>=25k: N=330 ROI=-0.8879% delta=-0.1215pp
- liq>=75k: N=286 ROI=-0.982% delta=-0.2156pp

## Missed-star scan
- Candidates: 1165
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 71, 'LIQ_LT_15K': 1047, 'VOL_LT_15K': 723, 'TX_LT_50': 588}

Research only; validate prospectively before changing production gates.
