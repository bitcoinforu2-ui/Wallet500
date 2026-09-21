# Wallet500 Cohort Research

Generated: 2026-09-21T07:42:27.214127+00:00
Source snapshot: 2026-09-21T07:35:52.130294+00:00

## Baseline
- N=359 ROI=-0.7396% P/L=$-2.655139

## Best post-hoc counterfactuals (min 5 retained)
- turnover<=1: N=193 ROI=-0.3692% delta=0.3704pp
- liq>=250k: N=128 ROI=-0.3864% delta=0.3532pp
- liq>=500k: N=174 ROI=-0.4421% delta=0.2975pp
- turnover<=2: N=285 ROI=-0.7254% delta=0.0142pp
- liq>=100k: N=232 ROI=-0.7381% delta=0.0015pp
- liq>=100k & vol>=50k: N=232 ROI=-0.7381% delta=0.0015pp
- vol>=50k: N=359 ROI=-0.7396% delta=0.0pp
- tx>=100: N=328 ROI=-0.8378% delta=-0.0982pp
- vol>=25k: N=330 ROI=-0.8587% delta=-0.1191pp
- liq>=75k: N=286 ROI=-0.9483% delta=-0.2087pp

## Missed-star scan
- Candidates: 1165
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 71, 'LIQ_LT_15K': 1047, 'VOL_LT_15K': 723, 'TX_LT_50': 588}

Research only; validate prospectively before changing production gates.
