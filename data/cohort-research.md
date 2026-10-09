# Wallet500 Cohort Research

Generated: 2026-10-09T21:08:44.708531+00:00
Source snapshot: 2026-10-09T21:01:45.378527+00:00

## Baseline
- N=359 ROI=-0.8369% P/L=$-3.004527

## Best post-hoc counterfactuals (min 5 retained)
- liq>=250k: N=128 ROI=-0.3864% delta=0.4505pp
- liq>=500k: N=174 ROI=-0.4421% delta=0.3948pp
- turnover<=1: N=193 ROI=-0.5503% delta=0.2866pp
- vol>=50k: N=359 ROI=-0.8369% delta=0.0pp
- turnover<=2: N=285 ROI=-0.848% delta=-0.0111pp
- liq>=100k: N=232 ROI=-0.8887% delta=-0.0518pp
- liq>=100k & vol>=50k: N=232 ROI=-0.8887% delta=-0.0518pp
- tx>=100: N=328 ROI=-0.9444% delta=-0.1075pp
- vol>=25k: N=330 ROI=-0.9646% delta=-0.1277pp
- liq>=75k: N=286 ROI=-1.0705% delta=-0.2336pp

## Missed-star scan
- Candidates: 1165
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 71, 'LIQ_LT_15K': 1047, 'VOL_LT_15K': 723, 'TX_LT_50': 588}

Research only; validate prospectively before changing production gates.
