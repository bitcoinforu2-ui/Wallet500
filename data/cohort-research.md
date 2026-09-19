# Wallet500 Cohort Research

Generated: 2026-09-19T02:05:00.875226+00:00
Source snapshot: 2026-09-19T01:58:30.455610+00:00

## Baseline
- N=359 ROI=-0.7865% P/L=$-2.82371

## Best post-hoc counterfactuals (min 5 retained)
- liq>=250k: N=128 ROI=-0.3864% delta=0.4001pp
- liq>=500k: N=174 ROI=-0.4421% delta=0.3444pp
- turnover<=1: N=193 ROI=-0.4566% delta=0.3299pp
- turnover<=2: N=285 ROI=-0.7845% delta=0.002pp
- vol>=50k: N=359 ROI=-0.7865% delta=0.0pp
- liq>=100k: N=232 ROI=-0.8107% delta=-0.0242pp
- liq>=100k & vol>=50k: N=232 ROI=-0.8107% delta=-0.0242pp
- tx>=100: N=328 ROI=-0.8892% delta=-0.1027pp
- vol>=25k: N=330 ROI=-0.9098% delta=-0.1233pp
- liq>=75k: N=286 ROI=-1.0073% delta=-0.2208pp

## Missed-star scan
- Candidates: 1165
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 71, 'LIQ_LT_15K': 1047, 'VOL_LT_15K': 723, 'TX_LT_50': 588}

Research only; validate prospectively before changing production gates.
