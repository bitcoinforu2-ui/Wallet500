# Wallet500 Cohort Research

Generated: 2026-09-29T01:29:11.237165+00:00
Source snapshot: 2026-09-29T01:22:36.640272+00:00

## Baseline
- N=359 ROI=-0.8013% P/L=$-2.876772

## Best post-hoc counterfactuals (min 5 retained)
- liq>=250k: N=128 ROI=-0.3864% delta=0.4149pp
- liq>=500k: N=174 ROI=-0.4421% delta=0.3592pp
- turnover<=1: N=193 ROI=-0.4841% delta=0.3172pp
- vol>=50k: N=359 ROI=-0.8013% delta=0.0pp
- turnover<=2: N=285 ROI=-0.8032% delta=-0.0019pp
- liq>=100k: N=232 ROI=-0.8336% delta=-0.0323pp
- liq>=100k & vol>=50k: N=232 ROI=-0.8336% delta=-0.0323pp
- tx>=100: N=328 ROI=-0.9054% delta=-0.1041pp
- vol>=25k: N=330 ROI=-0.9258% delta=-0.1245pp
- liq>=75k: N=286 ROI=-1.0258% delta=-0.2245pp

## Missed-star scan
- Candidates: 1165
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 71, 'LIQ_LT_15K': 1047, 'VOL_LT_15K': 723, 'TX_LT_50': 588}

Research only; validate prospectively before changing production gates.
