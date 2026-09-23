# Wallet500 Cohort Research

Generated: 2026-09-23T02:41:31.140005+00:00
Source snapshot: 2026-09-23T02:34:54.236141+00:00

## Baseline
- N=359 ROI=-0.749% P/L=$-2.689017

## Best post-hoc counterfactuals (min 5 retained)
- liq>=250k: N=128 ROI=-0.3864% delta=0.3626pp
- turnover<=1: N=193 ROI=-0.3868% delta=0.3622pp
- liq>=500k: N=174 ROI=-0.4421% delta=0.3069pp
- turnover<=2: N=285 ROI=-0.7373% delta=0.0117pp
- vol>=50k: N=359 ROI=-0.749% delta=0.0pp
- liq>=100k: N=232 ROI=-0.7527% delta=-0.0037pp
- liq>=100k & vol>=50k: N=232 ROI=-0.7527% delta=-0.0037pp
- tx>=100: N=328 ROI=-0.8482% delta=-0.0992pp
- vol>=25k: N=330 ROI=-0.8689% delta=-0.1199pp
- liq>=75k: N=286 ROI=-0.9602% delta=-0.2112pp

## Missed-star scan
- Candidates: 1165
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 71, 'LIQ_LT_15K': 1047, 'VOL_LT_15K': 723, 'TX_LT_50': 588}

Research only; validate prospectively before changing production gates.
