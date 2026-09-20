# Wallet500 Cohort Research

Generated: 2026-09-20T00:24:43.907468+00:00
Source snapshot: 2026-09-20T00:19:04.172108+00:00

## Baseline
- N=359 ROI=-1.0054% P/L=$-3.609425

## Best post-hoc counterfactuals (min 5 retained)
- turnover<=1: N=193 ROI=-0.3455% delta=0.6599pp
- liq>=250k: N=128 ROI=-0.3864% delta=0.619pp
- liq>=500k: N=174 ROI=-0.4421% delta=0.5633pp
- liq>=100k: N=232 ROI=-0.7184% delta=0.287pp
- liq>=100k & vol>=50k: N=232 ROI=-0.7184% delta=0.287pp
- liq>=75k: N=286 ROI=-0.9324% delta=0.073pp
- tx>=500: N=184 ROI=-0.9486% delta=0.0568pp
- tx>=250: N=283 ROI=-0.9701% delta=0.0353pp
- liq>=100k & tx>=250: N=182 ROI=-0.9905% delta=0.0149pp
- vol>=50k: N=359 ROI=-1.0054% delta=0.0pp

## Missed-star scan
- Candidates: 1165
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 71, 'LIQ_LT_15K': 1047, 'VOL_LT_15K': 723, 'TX_LT_50': 588}

Research only; validate prospectively before changing production gates.
