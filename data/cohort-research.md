# Wallet500 Cohort Research

Generated: 2026-09-19T05:36:26.639824+00:00
Source snapshot: 2026-09-19T05:30:26.826680+00:00

## Baseline
- N=359 ROI=-0.7435% P/L=$-2.669017

## Best post-hoc counterfactuals (min 5 retained)
- turnover<=1: N=193 ROI=-0.3764% delta=0.3671pp
- liq>=250k: N=128 ROI=-0.3864% delta=0.3571pp
- liq>=500k: N=174 ROI=-0.4421% delta=0.3014pp
- turnover<=2: N=285 ROI=-0.7303% delta=0.0132pp
- vol>=50k: N=359 ROI=-0.7435% delta=0.0pp
- liq>=100k: N=232 ROI=-0.7441% delta=-0.0006pp
- liq>=100k & vol>=50k: N=232 ROI=-0.7441% delta=-0.0006pp
- tx>=100: N=328 ROI=-0.8421% delta=-0.0986pp
- vol>=25k: N=330 ROI=-0.8629% delta=-0.1194pp
- liq>=75k: N=286 ROI=-0.9532% delta=-0.2097pp

## Missed-star scan
- Candidates: 1165
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 71, 'LIQ_LT_15K': 1047, 'VOL_LT_15K': 723, 'TX_LT_50': 588}

Research only; validate prospectively before changing production gates.
