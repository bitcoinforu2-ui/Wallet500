# Wallet500 Cohort Research

Generated: 2026-09-01T15:37:20.283573+00:00
Source snapshot: 2026-09-01T15:37:17.748277+00:00

## Baseline
- N=270 ROI=944.1539% P/L=$2549.215419

## Best post-hoc counterfactuals (min 5 retained)
- liq>=500k: N=63 ROI=4117.5197% delta=3173.3658pp
- liq>=250k & vol>=100k: N=90 ROI=2902.7465% delta=1958.5926pp
- liq>=250k: N=112 ROI=2333.2113% delta=1389.0574pp
- tx>=500: N=132 ROI=1966.244% delta=1022.0901pp
- liq>=100k & tx>=250: N=147 ROI=1765.2316% delta=821.0777pp
- turnover<=1: N=148 ROI=1749.2076% delta=805.0537pp
- liq>=100k & vol>=50k: N=155 ROI=1673.1425% delta=728.9886pp
- vol>=100k: N=161 ROI=1596.0673% delta=651.9134pp
- liq>=100k: N=189 ROI=1371.983% delta=427.8291pp
- turnover<=2: N=207 ROI=1229.027% delta=284.8731pp

## Missed-star scan
- Candidates: 959
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 65, 'LIQ_LT_50K': 853, 'VOL_LT_15K': 596, 'TX_LT_50': 480}

Research only; validate prospectively before changing production gates.
