# Wallet500 Cohort Research

Generated: 2026-09-19T09:25:48.251468+00:00
Source snapshot: 2026-09-19T09:19:46.556254+00:00

## Baseline
- N=359 ROI=-0.6943% P/L=$-2.49269

## Best post-hoc counterfactuals (min 5 retained)
- turnover<=1: N=193 ROI=-0.2851% delta=0.4092pp
- liq>=250k: N=128 ROI=-0.3864% delta=0.3079pp
- liq>=500k: N=174 ROI=-0.4421% delta=0.2522pp
- liq>=100k: N=232 ROI=-0.6681% delta=0.0262pp
- liq>=100k & vol>=50k: N=232 ROI=-0.6681% delta=0.0262pp
- turnover<=2: N=285 ROI=-0.6684% delta=0.0259pp
- vol>=50k: N=359 ROI=-0.6943% delta=0.0pp
- tx>=100: N=328 ROI=-0.7883% delta=-0.094pp
- vol>=25k: N=330 ROI=-0.8094% delta=-0.1151pp
- tx>=500: N=184 ROI=-0.8852% delta=-0.1909pp

## Missed-star scan
- Candidates: 1165
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 71, 'LIQ_LT_15K': 1047, 'VOL_LT_15K': 723, 'TX_LT_50': 588}

Research only; validate prospectively before changing production gates.
