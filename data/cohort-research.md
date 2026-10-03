# Wallet500 Cohort Research

Generated: 2026-10-03T22:19:20.406994+00:00
Source snapshot: 2026-10-03T22:12:38.727459+00:00

## Baseline
- N=359 ROI=-0.8042% P/L=$-2.886976

## Best post-hoc counterfactuals (min 5 retained)
- liq>=250k: N=128 ROI=-0.3864% delta=0.4178pp
- liq>=500k: N=174 ROI=-0.4421% delta=0.3621pp
- turnover<=1: N=193 ROI=-0.4894% delta=0.3148pp
- vol>=50k: N=359 ROI=-0.8042% delta=0.0pp
- turnover<=2: N=285 ROI=-0.8067% delta=-0.0025pp
- liq>=100k: N=232 ROI=-0.838% delta=-0.0338pp
- liq>=100k & vol>=50k: N=232 ROI=-0.838% delta=-0.0338pp
- tx>=100: N=328 ROI=-0.9085% delta=-0.1043pp
- vol>=25k: N=330 ROI=-0.9289% delta=-0.1247pp
- liq>=75k: N=286 ROI=-1.0294% delta=-0.2252pp

## Missed-star scan
- Candidates: 1165
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 71, 'LIQ_LT_15K': 1047, 'VOL_LT_15K': 723, 'TX_LT_50': 588}

Research only; validate prospectively before changing production gates.
