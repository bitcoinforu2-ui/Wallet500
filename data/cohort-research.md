# Wallet500 Cohort Research

Generated: 2026-09-30T08:28:48.538039+00:00
Source snapshot: 2026-09-30T08:22:18.999878+00:00

## Baseline
- N=359 ROI=-0.8% P/L=$-2.871874

## Best post-hoc counterfactuals (min 5 retained)
- liq>=250k: N=128 ROI=-0.3864% delta=0.4136pp
- liq>=500k: N=174 ROI=-0.4421% delta=0.3579pp
- turnover<=1: N=193 ROI=-0.4815% delta=0.3185pp
- vol>=50k: N=359 ROI=-0.8% delta=0.0pp
- turnover<=2: N=285 ROI=-0.8014% delta=-0.0014pp
- liq>=100k: N=232 ROI=-0.8315% delta=-0.0315pp
- liq>=100k & vol>=50k: N=232 ROI=-0.8315% delta=-0.0315pp
- tx>=100: N=328 ROI=-0.9039% delta=-0.1039pp
- vol>=25k: N=330 ROI=-0.9244% delta=-0.1244pp
- liq>=75k: N=286 ROI=-1.0241% delta=-0.2241pp

## Missed-star scan
- Candidates: 1165
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 71, 'LIQ_LT_15K': 1047, 'VOL_LT_15K': 723, 'TX_LT_50': 588}

Research only; validate prospectively before changing production gates.
