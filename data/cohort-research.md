# Wallet500 Cohort Research

Generated: 2026-09-14T15:00:21.523342+00:00
Source snapshot: 2026-09-14T14:54:18.442250+00:00

## Baseline
- N=359 ROI=-0.8101% P/L=$-2.9082

## Best post-hoc counterfactuals (min 5 retained)
- liq>=250k: N=128 ROI=-0.3864% delta=0.4237pp
- liq>=500k: N=174 ROI=-0.4421% delta=0.368pp
- turnover<=1: N=193 ROI=-0.5004% delta=0.3097pp
- vol>=50k: N=359 ROI=-0.8101% delta=0.0pp
- turnover<=2: N=285 ROI=-0.8142% delta=-0.0041pp
- liq>=100k: N=232 ROI=-0.8472% delta=-0.0371pp
- liq>=100k & vol>=50k: N=232 ROI=-0.8472% delta=-0.0371pp
- tx>=100: N=328 ROI=-0.915% delta=-0.1049pp
- vol>=25k: N=330 ROI=-0.9354% delta=-0.1253pp
- liq>=75k: N=286 ROI=-1.0368% delta=-0.2267pp

## Missed-star scan
- Candidates: 1165
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 71, 'LIQ_LT_15K': 1047, 'VOL_LT_15K': 723, 'TX_LT_50': 588}

Research only; validate prospectively before changing production gates.
