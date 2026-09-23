# Wallet500 Cohort Research

Generated: 2026-09-23T06:33:57.790367+00:00
Source snapshot: 2026-09-23T06:27:06.728900+00:00

## Baseline
- N=359 ROI=-0.7481% P/L=$-2.685751

## Best post-hoc counterfactuals (min 5 retained)
- turnover<=1: N=193 ROI=-0.3851% delta=0.363pp
- liq>=250k: N=128 ROI=-0.3864% delta=0.3617pp
- liq>=500k: N=174 ROI=-0.4421% delta=0.306pp
- turnover<=2: N=285 ROI=-0.7361% delta=0.012pp
- vol>=50k: N=359 ROI=-0.7481% delta=0.0pp
- liq>=100k: N=232 ROI=-0.7513% delta=-0.0032pp
- liq>=100k & vol>=50k: N=232 ROI=-0.7513% delta=-0.0032pp
- tx>=100: N=328 ROI=-0.8472% delta=-0.0991pp
- vol>=25k: N=330 ROI=-0.868% delta=-0.1199pp
- liq>=75k: N=286 ROI=-0.959% delta=-0.2109pp

## Missed-star scan
- Candidates: 1165
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 71, 'LIQ_LT_15K': 1047, 'VOL_LT_15K': 723, 'TX_LT_50': 588}

Research only; validate prospectively before changing production gates.
