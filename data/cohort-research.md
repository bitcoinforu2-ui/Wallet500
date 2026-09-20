# Wallet500 Cohort Research

Generated: 2026-09-20T04:06:12.160748+00:00
Source snapshot: 2026-09-20T04:00:31.837304+00:00

## Baseline
- N=359 ROI=-1.0347% P/L=$-3.714731

## Best post-hoc counterfactuals (min 5 retained)
- liq>=250k: N=128 ROI=-0.3864% delta=0.6483pp
- turnover<=1: N=193 ROI=-0.4001% delta=0.6346pp
- liq>=500k: N=174 ROI=-0.4421% delta=0.5926pp
- liq>=100k: N=232 ROI=-0.7638% delta=0.2709pp
- liq>=100k & vol>=50k: N=232 ROI=-0.7638% delta=0.2709pp
- liq>=75k: N=286 ROI=-0.9692% delta=0.0655pp
- tx>=500: N=184 ROI=-1.0059% delta=0.0288pp
- tx>=250: N=283 ROI=-1.0073% delta=0.0274pp
- vol>=50k: N=359 ROI=-1.0347% delta=0.0pp
- liq>=100k & tx>=250: N=182 ROI=-1.0483% delta=-0.0136pp

## Missed-star scan
- Candidates: 1165
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 71, 'LIQ_LT_15K': 1047, 'VOL_LT_15K': 723, 'TX_LT_50': 588}

Research only; validate prospectively before changing production gates.
