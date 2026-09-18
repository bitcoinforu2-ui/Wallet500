# Wallet500 Cohort Research

Generated: 2026-09-18T13:38:52.400146+00:00
Source snapshot: 2026-09-18T13:32:10.554098+00:00

## Baseline
- N=359 ROI=-0.8064% P/L=$-2.895139

## Best post-hoc counterfactuals (min 5 retained)
- liq>=250k: N=128 ROI=-0.3864% delta=0.42pp
- liq>=500k: N=174 ROI=-0.4421% delta=0.3643pp
- turnover<=1: N=193 ROI=-0.4936% delta=0.3128pp
- vol>=50k: N=359 ROI=-0.8064% delta=0.0pp
- turnover<=2: N=285 ROI=-0.8096% delta=-0.0032pp
- liq>=100k: N=232 ROI=-0.8415% delta=-0.0351pp
- liq>=100k & vol>=50k: N=232 ROI=-0.8415% delta=-0.0351pp
- tx>=100: N=328 ROI=-0.911% delta=-0.1046pp
- vol>=25k: N=330 ROI=-0.9314% delta=-0.125pp
- liq>=75k: N=286 ROI=-1.0323% delta=-0.2259pp

## Missed-star scan
- Candidates: 1165
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 71, 'LIQ_LT_15K': 1047, 'VOL_LT_15K': 723, 'TX_LT_50': 588}

Research only; validate prospectively before changing production gates.
