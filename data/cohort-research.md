# Wallet500 Cohort Research

Generated: 2026-09-18T14:54:25.964215+00:00
Source snapshot: 2026-09-18T14:48:15.347476+00:00

## Baseline
- N=359 ROI=-0.808% P/L=$-2.900853

## Best post-hoc counterfactuals (min 5 retained)
- liq>=250k: N=128 ROI=-0.3864% delta=0.4216pp
- liq>=500k: N=174 ROI=-0.4421% delta=0.3659pp
- turnover<=1: N=193 ROI=-0.4965% delta=0.3115pp
- vol>=50k: N=359 ROI=-0.808% delta=0.0pp
- turnover<=2: N=285 ROI=-0.8116% delta=-0.0036pp
- liq>=100k: N=232 ROI=-0.844% delta=-0.036pp
- liq>=100k & vol>=50k: N=232 ROI=-0.844% delta=-0.036pp
- tx>=100: N=328 ROI=-0.9128% delta=-0.1048pp
- vol>=25k: N=330 ROI=-0.9331% delta=-0.1251pp
- liq>=75k: N=286 ROI=-1.0343% delta=-0.2263pp

## Missed-star scan
- Candidates: 1165
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 71, 'LIQ_LT_15K': 1047, 'VOL_LT_15K': 723, 'TX_LT_50': 588}

Research only; validate prospectively before changing production gates.
