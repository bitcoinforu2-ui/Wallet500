# Wallet500 Cohort Research

Generated: 2026-09-23T18:09:26.762419+00:00
Source snapshot: 2026-09-23T18:03:13.460837+00:00

## Baseline
- N=359 ROI=-0.7544% P/L=$-2.7082

## Best post-hoc counterfactuals (min 5 retained)
- liq>=250k: N=128 ROI=-0.3864% delta=0.368pp
- turnover<=1: N=193 ROI=-0.3967% delta=0.3577pp
- liq>=500k: N=174 ROI=-0.4421% delta=0.3123pp
- turnover<=2: N=285 ROI=-0.744% delta=0.0104pp
- vol>=50k: N=359 ROI=-0.7544% delta=0.0pp
- liq>=100k: N=232 ROI=-0.761% delta=-0.0066pp
- liq>=100k & vol>=50k: N=232 ROI=-0.761% delta=-0.0066pp
- tx>=100: N=328 ROI=-0.854% delta=-0.0996pp
- vol>=25k: N=330 ROI=-0.8748% delta=-0.1204pp
- liq>=75k: N=286 ROI=-0.9669% delta=-0.2125pp

## Missed-star scan
- Candidates: 1165
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 71, 'LIQ_LT_15K': 1047, 'VOL_LT_15K': 723, 'TX_LT_50': 588}

Research only; validate prospectively before changing production gates.
