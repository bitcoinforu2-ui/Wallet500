# Wallet500 Cohort Research

Generated: 2026-09-19T19:35:48.754180+00:00
Source snapshot: 2026-09-19T19:29:27.844716+00:00

## Baseline
- N=359 ROI=-0.724% P/L=$-2.599221

## Best post-hoc counterfactuals (min 5 retained)
- turnover<=1: N=193 ROI=-0.3403% delta=0.3837pp
- liq>=250k: N=128 ROI=-0.3864% delta=0.3376pp
- liq>=500k: N=174 ROI=-0.4421% delta=0.2819pp
- turnover<=2: N=285 ROI=-0.7058% delta=0.0182pp
- liq>=100k: N=232 ROI=-0.714% delta=0.01pp
- liq>=100k & vol>=50k: N=232 ROI=-0.714% delta=0.01pp
- vol>=50k: N=359 ROI=-0.724% delta=0.0pp
- tx>=100: N=328 ROI=-0.8208% delta=-0.0968pp
- vol>=25k: N=330 ROI=-0.8417% delta=-0.1177pp
- liq>=75k: N=286 ROI=-0.9288% delta=-0.2048pp

## Missed-star scan
- Candidates: 1165
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 71, 'LIQ_LT_15K': 1047, 'VOL_LT_15K': 723, 'TX_LT_50': 588}

Research only; validate prospectively before changing production gates.
