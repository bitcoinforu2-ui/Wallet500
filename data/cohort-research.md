# Wallet500 Cohort Research

Generated: 2026-10-07T00:45:09.344498+00:00
Source snapshot: 2026-10-07T00:38:36.259380+00:00

## Baseline
- N=359 ROI=-0.8251% P/L=$-2.962078

## Best post-hoc counterfactuals (min 5 retained)
- liq>=250k: N=128 ROI=-0.3864% delta=0.4387pp
- liq>=500k: N=174 ROI=-0.4421% delta=0.383pp
- turnover<=1: N=193 ROI=-0.5283% delta=0.2968pp
- vol>=50k: N=359 ROI=-0.8251% delta=0.0pp
- turnover<=2: N=285 ROI=-0.8331% delta=-0.008pp
- liq>=100k: N=232 ROI=-0.8704% delta=-0.0453pp
- liq>=100k & vol>=50k: N=232 ROI=-0.8704% delta=-0.0453pp
- tx>=100: N=328 ROI=-0.9314% delta=-0.1063pp
- vol>=25k: N=330 ROI=-0.9517% delta=-0.1266pp
- liq>=75k: N=286 ROI=-1.0557% delta=-0.2306pp

## Missed-star scan
- Candidates: 1165
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 71, 'LIQ_LT_15K': 1047, 'VOL_LT_15K': 723, 'TX_LT_50': 588}

Research only; validate prospectively before changing production gates.
