# Wallet500 Cohort Research

Generated: 2026-09-19T05:05:58.749920+00:00
Source snapshot: 2026-09-19T04:59:37.224927+00:00

## Baseline
- N=359 ROI=-0.7423% P/L=$-2.664935

## Best post-hoc counterfactuals (min 5 retained)
- turnover<=1: N=193 ROI=-0.3743% delta=0.368pp
- liq>=250k: N=128 ROI=-0.3864% delta=0.3559pp
- liq>=500k: N=174 ROI=-0.4421% delta=0.3002pp
- turnover<=2: N=285 ROI=-0.7288% delta=0.0135pp
- vol>=50k: N=359 ROI=-0.7423% delta=0.0pp
- liq>=100k: N=232 ROI=-0.7423% delta=0.0pp
- liq>=100k & vol>=50k: N=232 ROI=-0.7423% delta=0.0pp
- tx>=100: N=328 ROI=-0.8408% delta=-0.0985pp
- vol>=25k: N=330 ROI=-0.8616% delta=-0.1193pp
- liq>=75k: N=286 ROI=-0.9518% delta=-0.2095pp

## Missed-star scan
- Candidates: 1165
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 71, 'LIQ_LT_15K': 1047, 'VOL_LT_15K': 723, 'TX_LT_50': 588}

Research only; validate prospectively before changing production gates.
