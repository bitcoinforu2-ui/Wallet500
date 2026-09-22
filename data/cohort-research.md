# Wallet500 Cohort Research

Generated: 2026-09-22T20:26:49.363260+00:00
Source snapshot: 2026-09-22T20:20:27.063893+00:00

## Baseline
- N=359 ROI=-0.7482% P/L=$-2.686159

## Best post-hoc counterfactuals (min 5 retained)
- turnover<=1: N=193 ROI=-0.3853% delta=0.3629pp
- liq>=250k: N=128 ROI=-0.3864% delta=0.3618pp
- liq>=500k: N=174 ROI=-0.4421% delta=0.3061pp
- turnover<=2: N=285 ROI=-0.7363% delta=0.0119pp
- vol>=50k: N=359 ROI=-0.7482% delta=0.0pp
- liq>=100k: N=232 ROI=-0.7515% delta=-0.0033pp
- liq>=100k & vol>=50k: N=232 ROI=-0.7515% delta=-0.0033pp
- tx>=100: N=328 ROI=-0.8473% delta=-0.0991pp
- vol>=25k: N=330 ROI=-0.8681% delta=-0.1199pp
- liq>=75k: N=286 ROI=-0.9592% delta=-0.211pp

## Missed-star scan
- Candidates: 1165
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 71, 'LIQ_LT_15K': 1047, 'VOL_LT_15K': 723, 'TX_LT_50': 588}

Research only; validate prospectively before changing production gates.
