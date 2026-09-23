# Wallet500 Cohort Research

Generated: 2026-09-23T05:10:03.496328+00:00
Source snapshot: 2026-09-23T05:02:47.134662+00:00

## Baseline
- N=359 ROI=-0.7469% P/L=$-2.681262

## Best post-hoc counterfactuals (min 5 retained)
- turnover<=1: N=193 ROI=-0.3828% delta=0.3641pp
- liq>=250k: N=128 ROI=-0.3864% delta=0.3605pp
- liq>=500k: N=174 ROI=-0.4421% delta=0.3048pp
- turnover<=2: N=285 ROI=-0.7346% delta=0.0123pp
- vol>=50k: N=359 ROI=-0.7469% delta=0.0pp
- liq>=100k: N=232 ROI=-0.7493% delta=-0.0024pp
- liq>=100k & vol>=50k: N=232 ROI=-0.7493% delta=-0.0024pp
- tx>=100: N=328 ROI=-0.8458% delta=-0.0989pp
- vol>=25k: N=330 ROI=-0.8666% delta=-0.1197pp
- liq>=75k: N=286 ROI=-0.9575% delta=-0.2106pp

## Missed-star scan
- Candidates: 1165
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 71, 'LIQ_LT_15K': 1047, 'VOL_LT_15K': 723, 'TX_LT_50': 588}

Research only; validate prospectively before changing production gates.
