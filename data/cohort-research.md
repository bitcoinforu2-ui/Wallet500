# Wallet500 Cohort Research

Generated: 2026-09-22T05:27:18.299151+00:00
Source snapshot: 2026-09-22T05:20:43.206763+00:00

## Baseline
- N=359 ROI=-0.7411% P/L=$-2.660445

## Best post-hoc counterfactuals (min 5 retained)
- turnover<=1: N=193 ROI=-0.372% delta=0.3691pp
- liq>=250k: N=128 ROI=-0.3864% delta=0.3547pp
- liq>=500k: N=174 ROI=-0.4421% delta=0.299pp
- turnover<=2: N=285 ROI=-0.7273% delta=0.0138pp
- liq>=100k: N=232 ROI=-0.7404% delta=0.0007pp
- liq>=100k & vol>=50k: N=232 ROI=-0.7404% delta=0.0007pp
- vol>=50k: N=359 ROI=-0.7411% delta=0.0pp
- tx>=100: N=328 ROI=-0.8395% delta=-0.0984pp
- vol>=25k: N=330 ROI=-0.8603% delta=-0.1192pp
- liq>=75k: N=286 ROI=-0.9502% delta=-0.2091pp

## Missed-star scan
- Candidates: 1165
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 71, 'LIQ_LT_15K': 1047, 'VOL_LT_15K': 723, 'TX_LT_50': 588}

Research only; validate prospectively before changing production gates.
