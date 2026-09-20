# Wallet500 Cohort Research

Generated: 2026-09-20T17:04:40.349881+00:00
Source snapshot: 2026-09-20T16:58:05.469278+00:00

## Baseline
- N=359 ROI=-1.0256% P/L=$-3.682078

## Best post-hoc counterfactuals (min 5 retained)
- turnover<=1: N=193 ROI=-0.3832% delta=0.6424pp
- liq>=250k: N=128 ROI=-0.3864% delta=0.6392pp
- liq>=500k: N=174 ROI=-0.4421% delta=0.5835pp
- liq>=100k: N=232 ROI=-0.7497% delta=0.2759pp
- liq>=100k & vol>=50k: N=232 ROI=-0.7497% delta=0.2759pp
- liq>=75k: N=286 ROI=-0.9578% delta=0.0678pp
- tx>=500: N=184 ROI=-0.9881% delta=0.0375pp
- tx>=250: N=283 ROI=-0.9958% delta=0.0298pp
- vol>=50k: N=359 ROI=-1.0256% delta=0.0pp
- liq>=100k & tx>=250: N=182 ROI=-1.0304% delta=-0.0048pp

## Missed-star scan
- Candidates: 1165
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 71, 'LIQ_LT_15K': 1047, 'VOL_LT_15K': 723, 'TX_LT_50': 588}

Research only; validate prospectively before changing production gates.
