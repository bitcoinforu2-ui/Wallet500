# Wallet500 Cohort Research

Generated: 2026-09-20T15:04:02.148270+00:00
Source snapshot: 2026-09-20T14:58:09.505925+00:00

## Baseline
- N=359 ROI=-1.026% P/L=$-3.683302

## Best post-hoc counterfactuals (min 5 retained)
- turnover<=1: N=193 ROI=-0.3838% delta=0.6422pp
- liq>=250k: N=128 ROI=-0.3864% delta=0.6396pp
- liq>=500k: N=174 ROI=-0.4421% delta=0.5839pp
- liq>=100k: N=232 ROI=-0.7502% delta=0.2758pp
- liq>=100k & vol>=50k: N=232 ROI=-0.7502% delta=0.2758pp
- liq>=75k: N=286 ROI=-0.9582% delta=0.0678pp
- tx>=500: N=184 ROI=-0.9888% delta=0.0372pp
- tx>=250: N=283 ROI=-0.9962% delta=0.0298pp
- vol>=50k: N=359 ROI=-1.026% delta=0.0pp
- liq>=100k & tx>=250: N=182 ROI=-1.031% delta=-0.005pp

## Missed-star scan
- Candidates: 1165
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 71, 'LIQ_LT_15K': 1047, 'VOL_LT_15K': 723, 'TX_LT_50': 588}

Research only; validate prospectively before changing production gates.
