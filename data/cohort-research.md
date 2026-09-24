# Wallet500 Cohort Research

Generated: 2026-09-24T17:28:59.494291+00:00
Source snapshot: 2026-09-24T17:22:12.631589+00:00

## Baseline
- N=359 ROI=-0.7648% P/L=$-2.745751

## Best post-hoc counterfactuals (min 5 retained)
- liq>=250k: N=128 ROI=-0.3864% delta=0.3784pp
- turnover<=1: N=193 ROI=-0.4162% delta=0.3486pp
- liq>=500k: N=174 ROI=-0.4421% delta=0.3227pp
- turnover<=2: N=285 ROI=-0.7572% delta=0.0076pp
- vol>=50k: N=359 ROI=-0.7648% delta=0.0pp
- liq>=100k: N=232 ROI=-0.7771% delta=-0.0123pp
- liq>=100k & vol>=50k: N=232 ROI=-0.7771% delta=-0.0123pp
- tx>=100: N=328 ROI=-0.8655% delta=-0.1007pp
- vol>=25k: N=330 ROI=-0.8861% delta=-0.1213pp
- liq>=75k: N=286 ROI=-0.98% delta=-0.2152pp

## Missed-star scan
- Candidates: 1165
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 71, 'LIQ_LT_15K': 1047, 'VOL_LT_15K': 723, 'TX_LT_50': 588}

Research only; validate prospectively before changing production gates.
