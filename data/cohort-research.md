# Wallet500 Cohort Research

Generated: 2026-09-17T17:42:15.923039+00:00
Source snapshot: 2026-09-17T17:35:30.637475+00:00

## Baseline
- N=359 ROI=-0.8121% P/L=$-2.915547

## Best post-hoc counterfactuals (min 5 retained)
- liq>=250k: N=128 ROI=-0.3864% delta=0.4257pp
- liq>=500k: N=174 ROI=-0.4421% delta=0.37pp
- turnover<=1: N=193 ROI=-0.5042% delta=0.3079pp
- vol>=50k: N=359 ROI=-0.8121% delta=0.0pp
- turnover<=2: N=285 ROI=-0.8168% delta=-0.0047pp
- liq>=100k: N=232 ROI=-0.8503% delta=-0.0382pp
- liq>=100k & vol>=50k: N=232 ROI=-0.8503% delta=-0.0382pp
- tx>=100: N=328 ROI=-0.9172% delta=-0.1051pp
- vol>=25k: N=330 ROI=-0.9376% delta=-0.1255pp
- liq>=75k: N=286 ROI=-1.0394% delta=-0.2273pp

## Missed-star scan
- Candidates: 1165
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 71, 'LIQ_LT_15K': 1047, 'VOL_LT_15K': 723, 'TX_LT_50': 588}

Research only; validate prospectively before changing production gates.
