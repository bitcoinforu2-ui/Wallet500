# Wallet500 Cohort Research

Generated: 2026-09-29T14:10:26.850149+00:00
Source snapshot: 2026-09-29T14:03:44.890268+00:00

## Baseline
- N=359 ROI=-0.8038% P/L=$-2.885751

## Best post-hoc counterfactuals (min 5 retained)
- liq>=250k: N=128 ROI=-0.3864% delta=0.4174pp
- liq>=500k: N=174 ROI=-0.4421% delta=0.3617pp
- turnover<=1: N=193 ROI=-0.4887% delta=0.3151pp
- vol>=50k: N=359 ROI=-0.8038% delta=0.0pp
- turnover<=2: N=285 ROI=-0.8063% delta=-0.0025pp
- liq>=100k: N=232 ROI=-0.8375% delta=-0.0337pp
- liq>=100k & vol>=50k: N=232 ROI=-0.8375% delta=-0.0337pp
- tx>=100: N=328 ROI=-0.9082% delta=-0.1044pp
- vol>=25k: N=330 ROI=-0.9286% delta=-0.1248pp
- liq>=75k: N=286 ROI=-1.029% delta=-0.2252pp

## Missed-star scan
- Candidates: 1165
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 71, 'LIQ_LT_15K': 1047, 'VOL_LT_15K': 723, 'TX_LT_50': 588}

Research only; validate prospectively before changing production gates.
