# Wallet500 Cohort Research

Generated: 2026-09-24T08:44:47.243213+00:00
Source snapshot: 2026-09-24T08:38:22.533714+00:00

## Baseline
- N=359 ROI=-0.7584% P/L=$-2.722486

## Best post-hoc counterfactuals (min 5 retained)
- liq>=250k: N=128 ROI=-0.3864% delta=0.372pp
- turnover<=1: N=193 ROI=-0.4041% delta=0.3543pp
- liq>=500k: N=174 ROI=-0.4421% delta=0.3163pp
- turnover<=2: N=285 ROI=-0.749% delta=0.0094pp
- vol>=50k: N=359 ROI=-0.7584% delta=0.0pp
- liq>=100k: N=232 ROI=-0.7671% delta=-0.0087pp
- liq>=100k & vol>=50k: N=232 ROI=-0.7671% delta=-0.0087pp
- tx>=100: N=328 ROI=-0.8584% delta=-0.1pp
- vol>=25k: N=330 ROI=-0.8791% delta=-0.1207pp
- liq>=75k: N=286 ROI=-0.9719% delta=-0.2135pp

## Missed-star scan
- Candidates: 1165
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 71, 'LIQ_LT_15K': 1047, 'VOL_LT_15K': 723, 'TX_LT_50': 588}

Research only; validate prospectively before changing production gates.
