# Wallet500 Cohort Research

Generated: 2026-09-17T21:01:53.473647+00:00
Source snapshot: 2026-09-17T20:55:26.136655+00:00

## Baseline
- N=359 ROI=-0.8111% P/L=$-2.911874

## Best post-hoc counterfactuals (min 5 retained)
- liq>=250k: N=128 ROI=-0.3864% delta=0.4247pp
- liq>=500k: N=174 ROI=-0.4421% delta=0.369pp
- turnover<=1: N=193 ROI=-0.5023% delta=0.3088pp
- vol>=50k: N=359 ROI=-0.8111% delta=0.0pp
- turnover<=2: N=285 ROI=-0.8155% delta=-0.0044pp
- liq>=100k: N=232 ROI=-0.8487% delta=-0.0376pp
- liq>=100k & vol>=50k: N=232 ROI=-0.8487% delta=-0.0376pp
- tx>=100: N=328 ROI=-0.9161% delta=-0.105pp
- vol>=25k: N=330 ROI=-0.9365% delta=-0.1254pp
- liq>=75k: N=286 ROI=-1.0381% delta=-0.227pp

## Missed-star scan
- Candidates: 1165
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 71, 'LIQ_LT_15K': 1047, 'VOL_LT_15K': 723, 'TX_LT_50': 588}

Research only; validate prospectively before changing production gates.
