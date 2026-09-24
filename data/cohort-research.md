# Wallet500 Cohort Research

Generated: 2026-09-24T12:50:05.680967+00:00
Source snapshot: 2026-09-24T12:43:51.650616+00:00

## Baseline
- N=359 ROI=-0.7671% P/L=$-2.753915

## Best post-hoc counterfactuals (min 5 retained)
- liq>=250k: N=128 ROI=-0.3864% delta=0.3807pp
- turnover<=1: N=193 ROI=-0.4204% delta=0.3467pp
- liq>=500k: N=174 ROI=-0.4421% delta=0.325pp
- turnover<=2: N=285 ROI=-0.7601% delta=0.007pp
- vol>=50k: N=359 ROI=-0.7671% delta=0.0pp
- liq>=100k: N=232 ROI=-0.7807% delta=-0.0136pp
- liq>=100k & vol>=50k: N=232 ROI=-0.7807% delta=-0.0136pp
- tx>=100: N=328 ROI=-0.868% delta=-0.1009pp
- vol>=25k: N=330 ROI=-0.8886% delta=-0.1215pp
- liq>=75k: N=286 ROI=-0.9829% delta=-0.2158pp

## Missed-star scan
- Candidates: 1165
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 71, 'LIQ_LT_15K': 1047, 'VOL_LT_15K': 723, 'TX_LT_50': 588}

Research only; validate prospectively before changing production gates.
