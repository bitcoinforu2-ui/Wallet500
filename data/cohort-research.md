# Wallet500 Cohort Research

Generated: 2026-10-03T06:33:49.538978+00:00
Source snapshot: 2026-10-03T06:27:31.315314+00:00

## Baseline
- N=359 ROI=-0.8022% P/L=$-2.880037

## Best post-hoc counterfactuals (min 5 retained)
- liq>=250k: N=128 ROI=-0.3864% delta=0.4158pp
- liq>=500k: N=174 ROI=-0.4421% delta=0.3601pp
- turnover<=1: N=193 ROI=-0.4858% delta=0.3164pp
- vol>=50k: N=359 ROI=-0.8022% delta=0.0pp
- turnover<=2: N=285 ROI=-0.8043% delta=-0.0021pp
- liq>=100k: N=232 ROI=-0.835% delta=-0.0328pp
- liq>=100k & vol>=50k: N=232 ROI=-0.835% delta=-0.0328pp
- tx>=100: N=328 ROI=-0.9064% delta=-0.1042pp
- vol>=25k: N=330 ROI=-0.9268% delta=-0.1246pp
- liq>=75k: N=286 ROI=-1.027% delta=-0.2248pp

## Missed-star scan
- Candidates: 1165
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 71, 'LIQ_LT_15K': 1047, 'VOL_LT_15K': 723, 'TX_LT_50': 588}

Research only; validate prospectively before changing production gates.
