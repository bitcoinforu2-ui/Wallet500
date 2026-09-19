# Wallet500 Cohort Research

Generated: 2026-09-19T04:55:42.162373+00:00
Source snapshot: 2026-09-19T04:49:19.202189+00:00

## Baseline
- N=359 ROI=-0.7457% P/L=$-2.67718

## Best post-hoc counterfactuals (min 5 retained)
- turnover<=1: N=193 ROI=-0.3807% delta=0.365pp
- liq>=250k: N=128 ROI=-0.3864% delta=0.3593pp
- liq>=500k: N=174 ROI=-0.4421% delta=0.3036pp
- turnover<=2: N=285 ROI=-0.7331% delta=0.0126pp
- vol>=50k: N=359 ROI=-0.7457% delta=0.0pp
- liq>=100k: N=232 ROI=-0.7476% delta=-0.0019pp
- liq>=100k & vol>=50k: N=232 ROI=-0.7476% delta=-0.0019pp
- tx>=100: N=328 ROI=-0.8446% delta=-0.0989pp
- vol>=25k: N=330 ROI=-0.8654% delta=-0.1197pp
- liq>=75k: N=286 ROI=-0.956% delta=-0.2103pp

## Missed-star scan
- Candidates: 1165
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 71, 'LIQ_LT_15K': 1047, 'VOL_LT_15K': 723, 'TX_LT_50': 588}

Research only; validate prospectively before changing production gates.
