# Wallet500 Cohort Research

Generated: 2026-09-20T04:29:33.976924+00:00
Source snapshot: 2026-09-20T04:22:58.308586+00:00

## Baseline
- N=359 ROI=-1.0345% P/L=$-3.713915

## Best post-hoc counterfactuals (min 5 retained)
- liq>=250k: N=128 ROI=-0.3864% delta=0.6481pp
- turnover<=1: N=193 ROI=-0.3997% delta=0.6348pp
- liq>=500k: N=174 ROI=-0.4421% delta=0.5924pp
- liq>=100k: N=232 ROI=-0.7634% delta=0.2711pp
- liq>=100k & vol>=50k: N=232 ROI=-0.7634% delta=0.2711pp
- liq>=75k: N=286 ROI=-0.9689% delta=0.0656pp
- tx>=500: N=184 ROI=-1.0054% delta=0.0291pp
- tx>=250: N=283 ROI=-1.007% delta=0.0275pp
- vol>=50k: N=359 ROI=-1.0345% delta=0.0pp
- liq>=100k & tx>=250: N=182 ROI=-1.0479% delta=-0.0134pp

## Missed-star scan
- Candidates: 1165
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 71, 'LIQ_LT_15K': 1047, 'VOL_LT_15K': 723, 'TX_LT_50': 588}

Research only; validate prospectively before changing production gates.
