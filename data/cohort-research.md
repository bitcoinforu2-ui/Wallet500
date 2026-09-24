# Wallet500 Cohort Research

Generated: 2026-09-24T15:31:31.893649+00:00
Source snapshot: 2026-09-24T15:24:57.613278+00:00

## Baseline
- N=359 ROI=-0.7637% P/L=$-2.74167

## Best post-hoc counterfactuals (min 5 retained)
- liq>=250k: N=128 ROI=-0.3864% delta=0.3773pp
- turnover<=1: N=193 ROI=-0.4141% delta=0.3496pp
- liq>=500k: N=174 ROI=-0.4421% delta=0.3216pp
- turnover<=2: N=285 ROI=-0.7558% delta=0.0079pp
- vol>=50k: N=359 ROI=-0.7637% delta=0.0pp
- liq>=100k: N=232 ROI=-0.7754% delta=-0.0117pp
- liq>=100k & vol>=50k: N=232 ROI=-0.7754% delta=-0.0117pp
- tx>=100: N=328 ROI=-0.8642% delta=-0.1005pp
- vol>=25k: N=330 ROI=-0.8849% delta=-0.1212pp
- liq>=75k: N=286 ROI=-0.9786% delta=-0.2149pp

## Missed-star scan
- Candidates: 1165
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 71, 'LIQ_LT_15K': 1047, 'VOL_LT_15K': 723, 'TX_LT_50': 588}

Research only; validate prospectively before changing production gates.
