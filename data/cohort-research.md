# Wallet500 Cohort Research

Generated: 2026-09-18T18:54:22.599354+00:00
Source snapshot: 2026-09-18T18:47:18.883550+00:00

## Baseline
- N=359 ROI=-0.7968% P/L=$-2.860445

## Best post-hoc counterfactuals (min 5 retained)
- liq>=250k: N=128 ROI=-0.3864% delta=0.4104pp
- liq>=500k: N=174 ROI=-0.4421% delta=0.3547pp
- turnover<=1: N=193 ROI=-0.4756% delta=0.3212pp
- vol>=50k: N=359 ROI=-0.7968% delta=0.0pp
- turnover<=2: N=285 ROI=-0.7974% delta=-0.0006pp
- liq>=100k: N=232 ROI=-0.8266% delta=-0.0298pp
- liq>=100k & vol>=50k: N=232 ROI=-0.8266% delta=-0.0298pp
- tx>=100: N=328 ROI=-0.9004% delta=-0.1036pp
- vol>=25k: N=330 ROI=-0.9209% delta=-0.1241pp
- liq>=75k: N=286 ROI=-1.0201% delta=-0.2233pp

## Missed-star scan
- Candidates: 1165
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 71, 'LIQ_LT_15K': 1047, 'VOL_LT_15K': 723, 'TX_LT_50': 588}

Research only; validate prospectively before changing production gates.
