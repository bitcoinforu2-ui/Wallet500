# Wallet500 Cohort Research

Generated: 2026-09-20T07:46:00.502806+00:00
Source snapshot: 2026-09-20T07:39:47.978528+00:00

## Baseline
- N=359 ROI=-1.0312% P/L=$-3.702078

## Best post-hoc counterfactuals (min 5 retained)
- liq>=250k: N=128 ROI=-0.3864% delta=0.6448pp
- turnover<=1: N=193 ROI=-0.3936% delta=0.6376pp
- liq>=500k: N=174 ROI=-0.4421% delta=0.5891pp
- liq>=100k: N=232 ROI=-0.7583% delta=0.2729pp
- liq>=100k & vol>=50k: N=232 ROI=-0.7583% delta=0.2729pp
- liq>=75k: N=286 ROI=-0.9647% delta=0.0665pp
- tx>=500: N=184 ROI=-0.999% delta=0.0322pp
- tx>=250: N=283 ROI=-1.0028% delta=0.0284pp
- vol>=50k: N=359 ROI=-1.0312% delta=0.0pp
- liq>=100k & tx>=250: N=182 ROI=-1.0414% delta=-0.0102pp

## Missed-star scan
- Candidates: 1165
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 71, 'LIQ_LT_15K': 1047, 'VOL_LT_15K': 723, 'TX_LT_50': 588}

Research only; validate prospectively before changing production gates.
