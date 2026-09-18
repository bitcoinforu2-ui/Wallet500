# Wallet500 Cohort Research

Generated: 2026-09-18T19:05:48.110551+00:00
Source snapshot: 2026-09-18T18:59:13.693068+00:00

## Baseline
- N=359 ROI=-0.7925% P/L=$-2.844935

## Best post-hoc counterfactuals (min 5 retained)
- liq>=250k: N=128 ROI=-0.3864% delta=0.4061pp
- liq>=500k: N=174 ROI=-0.4421% delta=0.3504pp
- turnover<=1: N=193 ROI=-0.4676% delta=0.3249pp
- turnover<=2: N=285 ROI=-0.792% delta=0.0005pp
- vol>=50k: N=359 ROI=-0.7925% delta=0.0pp
- liq>=100k: N=232 ROI=-0.8199% delta=-0.0274pp
- liq>=100k & vol>=50k: N=232 ROI=-0.8199% delta=-0.0274pp
- tx>=100: N=328 ROI=-0.8957% delta=-0.1032pp
- vol>=25k: N=330 ROI=-0.9162% delta=-0.1237pp
- liq>=75k: N=286 ROI=-1.0147% delta=-0.2222pp

## Missed-star scan
- Candidates: 1165
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 71, 'LIQ_LT_15K': 1047, 'VOL_LT_15K': 723, 'TX_LT_50': 588}

Research only; validate prospectively before changing production gates.
