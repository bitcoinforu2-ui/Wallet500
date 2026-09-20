# Wallet500 Cohort Research

Generated: 2026-09-20T06:59:14.326507+00:00
Source snapshot: 2026-09-20T06:52:49.283695+00:00

## Baseline
- N=359 ROI=-1.0316% P/L=$-3.703302

## Best post-hoc counterfactuals (min 5 retained)
- liq>=250k: N=128 ROI=-0.3864% delta=0.6452pp
- turnover<=1: N=193 ROI=-0.3942% delta=0.6374pp
- liq>=500k: N=174 ROI=-0.4421% delta=0.5895pp
- liq>=100k: N=232 ROI=-0.7588% delta=0.2728pp
- liq>=100k & vol>=50k: N=232 ROI=-0.7588% delta=0.2728pp
- liq>=75k: N=286 ROI=-0.9652% delta=0.0664pp
- tx>=500: N=184 ROI=-0.9997% delta=0.0319pp
- tx>=250: N=283 ROI=-1.0033% delta=0.0283pp
- vol>=50k: N=359 ROI=-1.0316% delta=0.0pp
- liq>=100k & tx>=250: N=182 ROI=-1.042% delta=-0.0104pp

## Missed-star scan
- Candidates: 1165
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 71, 'LIQ_LT_15K': 1047, 'VOL_LT_15K': 723, 'TX_LT_50': 588}

Research only; validate prospectively before changing production gates.
