# Wallet500 Cohort Research

Generated: 2026-10-07T06:33:47.179835+00:00
Source snapshot: 2026-10-07T06:27:19.088427+00:00

## Baseline
- N=359 ROI=-0.8253% P/L=$-2.962894

## Best post-hoc counterfactuals (min 5 retained)
- liq>=250k: N=128 ROI=-0.3864% delta=0.4389pp
- liq>=500k: N=174 ROI=-0.4421% delta=0.3832pp
- turnover<=1: N=193 ROI=-0.5287% delta=0.2966pp
- vol>=50k: N=359 ROI=-0.8253% delta=0.0pp
- turnover<=2: N=285 ROI=-0.8334% delta=-0.0081pp
- liq>=100k: N=232 ROI=-0.8707% delta=-0.0454pp
- liq>=100k & vol>=50k: N=232 ROI=-0.8707% delta=-0.0454pp
- tx>=100: N=328 ROI=-0.9317% delta=-0.1064pp
- vol>=25k: N=330 ROI=-0.9519% delta=-0.1266pp
- liq>=75k: N=286 ROI=-1.0559% delta=-0.2306pp

## Missed-star scan
- Candidates: 1165
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 71, 'LIQ_LT_15K': 1047, 'VOL_LT_15K': 723, 'TX_LT_50': 588}

Research only; validate prospectively before changing production gates.
