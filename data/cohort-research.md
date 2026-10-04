# Wallet500 Cohort Research

Generated: 2026-10-04T06:36:05.244065+00:00
Source snapshot: 2026-10-04T06:29:16.515574+00:00

## Baseline
- N=359 ROI=-0.8028% P/L=$-2.882078

## Best post-hoc counterfactuals (min 5 retained)
- liq>=250k: N=128 ROI=-0.3864% delta=0.4164pp
- liq>=500k: N=174 ROI=-0.4421% delta=0.3607pp
- turnover<=1: N=193 ROI=-0.4868% delta=0.316pp
- vol>=50k: N=359 ROI=-0.8028% delta=0.0pp
- turnover<=2: N=285 ROI=-0.805% delta=-0.0022pp
- liq>=100k: N=232 ROI=-0.8359% delta=-0.0331pp
- liq>=100k & vol>=50k: N=232 ROI=-0.8359% delta=-0.0331pp
- tx>=100: N=328 ROI=-0.907% delta=-0.1042pp
- vol>=25k: N=330 ROI=-0.9274% delta=-0.1246pp
- liq>=75k: N=286 ROI=-1.0277% delta=-0.2249pp

## Missed-star scan
- Candidates: 1165
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 71, 'LIQ_LT_15K': 1047, 'VOL_LT_15K': 723, 'TX_LT_50': 588}

Research only; validate prospectively before changing production gates.
