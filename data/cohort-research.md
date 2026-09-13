# Wallet500 Cohort Research

Generated: 2026-09-13T14:36:30.071174+00:00
Source snapshot: 2026-09-13T14:30:35.642733+00:00

## Baseline
- N=359 ROI=-0.806% P/L=$-2.893506

## Best post-hoc counterfactuals (min 5 retained)
- liq>=250k: N=128 ROI=-0.3864% delta=0.4196pp
- liq>=500k: N=174 ROI=-0.4421% delta=0.3639pp
- turnover<=1: N=193 ROI=-0.4927% delta=0.3133pp
- vol>=50k: N=359 ROI=-0.806% delta=0.0pp
- turnover<=2: N=285 ROI=-0.809% delta=-0.003pp
- liq>=100k: N=232 ROI=-0.8408% delta=-0.0348pp
- liq>=100k & vol>=50k: N=232 ROI=-0.8408% delta=-0.0348pp
- tx>=100: N=328 ROI=-0.9105% delta=-0.1045pp
- vol>=25k: N=330 ROI=-0.9309% delta=-0.1249pp
- liq>=75k: N=286 ROI=-1.0317% delta=-0.2257pp

## Missed-star scan
- Candidates: 1165
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 71, 'LIQ_LT_15K': 1047, 'VOL_LT_15K': 723, 'TX_LT_50': 588}

Research only; validate prospectively before changing production gates.
