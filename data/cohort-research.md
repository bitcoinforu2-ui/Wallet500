# Wallet500 Cohort Research

Generated: 2026-09-23T06:59:49.164879+00:00
Source snapshot: 2026-09-23T06:53:20.136376+00:00

## Baseline
- N=359 ROI=-0.7479% P/L=$-2.684935

## Best post-hoc counterfactuals (min 5 retained)
- turnover<=1: N=193 ROI=-0.3847% delta=0.3632pp
- liq>=250k: N=128 ROI=-0.3864% delta=0.3615pp
- liq>=500k: N=174 ROI=-0.4421% delta=0.3058pp
- turnover<=2: N=285 ROI=-0.7359% delta=0.012pp
- vol>=50k: N=359 ROI=-0.7479% delta=0.0pp
- liq>=100k: N=232 ROI=-0.7509% delta=-0.003pp
- liq>=100k & vol>=50k: N=232 ROI=-0.7509% delta=-0.003pp
- tx>=100: N=328 ROI=-0.8469% delta=-0.099pp
- vol>=25k: N=330 ROI=-0.8677% delta=-0.1198pp
- liq>=75k: N=286 ROI=-0.9588% delta=-0.2109pp

## Missed-star scan
- Candidates: 1165
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 71, 'LIQ_LT_15K': 1047, 'VOL_LT_15K': 723, 'TX_LT_50': 588}

Research only; validate prospectively before changing production gates.
