# Wallet500 Cohort Research

Generated: 2026-09-24T14:10:39.641821+00:00
Source snapshot: 2026-09-24T14:04:07.651450+00:00

## Baseline
- N=359 ROI=-0.767% P/L=$-2.753506

## Best post-hoc counterfactuals (min 5 retained)
- liq>=250k: N=128 ROI=-0.3864% delta=0.3806pp
- turnover<=1: N=193 ROI=-0.4202% delta=0.3468pp
- liq>=500k: N=174 ROI=-0.4421% delta=0.3249pp
- turnover<=2: N=285 ROI=-0.7599% delta=0.0071pp
- vol>=50k: N=359 ROI=-0.767% delta=0.0pp
- liq>=100k: N=232 ROI=-0.7805% delta=-0.0135pp
- liq>=100k & vol>=50k: N=232 ROI=-0.7805% delta=-0.0135pp
- tx>=100: N=328 ROI=-0.8678% delta=-0.1008pp
- vol>=25k: N=330 ROI=-0.8885% delta=-0.1215pp
- liq>=75k: N=286 ROI=-0.9827% delta=-0.2157pp

## Missed-star scan
- Candidates: 1165
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 71, 'LIQ_LT_15K': 1047, 'VOL_LT_15K': 723, 'TX_LT_50': 588}

Research only; validate prospectively before changing production gates.
