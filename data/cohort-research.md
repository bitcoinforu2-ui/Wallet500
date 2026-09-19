# Wallet500 Cohort Research

Generated: 2026-09-19T11:13:48.767036+00:00
Source snapshot: 2026-09-19T11:06:57.122438+00:00

## Baseline
- N=359 ROI=-0.6995% P/L=$-2.511057

## Best post-hoc counterfactuals (min 5 retained)
- turnover<=1: N=193 ROI=-0.2946% delta=0.4049pp
- liq>=250k: N=128 ROI=-0.3864% delta=0.3131pp
- liq>=500k: N=174 ROI=-0.4421% delta=0.2574pp
- turnover<=2: N=285 ROI=-0.6748% delta=0.0247pp
- liq>=100k: N=232 ROI=-0.676% delta=0.0235pp
- liq>=100k & vol>=50k: N=232 ROI=-0.676% delta=0.0235pp
- vol>=50k: N=359 ROI=-0.6995% delta=0.0pp
- tx>=100: N=328 ROI=-0.7939% delta=-0.0944pp
- vol>=25k: N=330 ROI=-0.815% delta=-0.1155pp
- tx>=500: N=184 ROI=-0.8952% delta=-0.1957pp

## Missed-star scan
- Candidates: 1165
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 71, 'LIQ_LT_15K': 1047, 'VOL_LT_15K': 723, 'TX_LT_50': 588}

Research only; validate prospectively before changing production gates.
