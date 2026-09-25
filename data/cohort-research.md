# Wallet500 Cohort Research

Generated: 2026-09-25T13:57:14.449358+00:00
Source snapshot: 2026-09-25T13:50:51.096696+00:00

## Baseline
- N=359 ROI=-0.777% P/L=$-2.789425

## Best post-hoc counterfactuals (min 5 retained)
- liq>=250k: N=128 ROI=-0.3864% delta=0.3906pp
- turnover<=1: N=193 ROI=-0.4388% delta=0.3382pp
- liq>=500k: N=174 ROI=-0.4421% delta=0.3349pp
- turnover<=2: N=285 ROI=-0.7725% delta=0.0045pp
- vol>=50k: N=359 ROI=-0.777% delta=0.0pp
- liq>=100k: N=232 ROI=-0.796% delta=-0.019pp
- liq>=100k & vol>=50k: N=232 ROI=-0.796% delta=-0.019pp
- tx>=100: N=328 ROI=-0.8788% delta=-0.1018pp
- vol>=25k: N=330 ROI=-0.8994% delta=-0.1224pp
- liq>=75k: N=286 ROI=-0.9953% delta=-0.2183pp

## Missed-star scan
- Candidates: 1165
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 71, 'LIQ_LT_15K': 1047, 'VOL_LT_15K': 723, 'TX_LT_50': 588}

Research only; validate prospectively before changing production gates.
