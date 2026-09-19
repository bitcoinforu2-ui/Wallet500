# Wallet500 Cohort Research

Generated: 2026-09-19T08:38:52.512650+00:00
Source snapshot: 2026-09-19T08:32:52.972881+00:00

## Baseline
- N=359 ROI=-0.713% P/L=$-2.559629

## Best post-hoc counterfactuals (min 5 retained)
- turnover<=1: N=193 ROI=-0.3197% delta=0.3933pp
- liq>=250k: N=128 ROI=-0.3864% delta=0.3266pp
- liq>=500k: N=174 ROI=-0.4421% delta=0.2709pp
- turnover<=2: N=285 ROI=-0.6919% delta=0.0211pp
- liq>=100k: N=232 ROI=-0.6969% delta=0.0161pp
- liq>=100k & vol>=50k: N=232 ROI=-0.6969% delta=0.0161pp
- vol>=50k: N=359 ROI=-0.713% delta=0.0pp
- tx>=100: N=328 ROI=-0.8087% delta=-0.0957pp
- vol>=25k: N=330 ROI=-0.8297% delta=-0.1167pp
- liq>=75k: N=286 ROI=-0.9149% delta=-0.2019pp

## Missed-star scan
- Candidates: 1165
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 71, 'LIQ_LT_15K': 1047, 'VOL_LT_15K': 723, 'TX_LT_50': 588}

Research only; validate prospectively before changing production gates.
