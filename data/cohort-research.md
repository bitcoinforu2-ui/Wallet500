# Wallet500 Cohort Research

Generated: 2026-09-21T15:53:42.592076+00:00
Source snapshot: 2026-09-21T15:47:19.731764+00:00

## Baseline
- N=359 ROI=-0.73% P/L=$-2.620853

## Best post-hoc counterfactuals (min 5 retained)
- turnover<=1: N=193 ROI=-0.3515% delta=0.3785pp
- liq>=250k: N=128 ROI=-0.3864% delta=0.3436pp
- liq>=500k: N=174 ROI=-0.4421% delta=0.2879pp
- turnover<=2: N=285 ROI=-0.7134% delta=0.0166pp
- liq>=100k: N=232 ROI=-0.7233% delta=0.0067pp
- liq>=100k & vol>=50k: N=232 ROI=-0.7233% delta=0.0067pp
- vol>=50k: N=359 ROI=-0.73% delta=0.0pp
- tx>=100: N=328 ROI=-0.8274% delta=-0.0974pp
- vol>=25k: N=330 ROI=-0.8483% delta=-0.1183pp
- liq>=75k: N=286 ROI=-0.9363% delta=-0.2063pp

## Missed-star scan
- Candidates: 1165
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 71, 'LIQ_LT_15K': 1047, 'VOL_LT_15K': 723, 'TX_LT_50': 588}

Research only; validate prospectively before changing production gates.
