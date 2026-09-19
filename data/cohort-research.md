# Wallet500 Cohort Research

Generated: 2026-09-19T02:40:56.706695+00:00
Source snapshot: 2026-09-19T02:34:45.621093+00:00

## Baseline
- N=359 ROI=-0.78% P/L=$-2.800037

## Best post-hoc counterfactuals (min 5 retained)
- liq>=250k: N=128 ROI=-0.3864% delta=0.3936pp
- liq>=500k: N=174 ROI=-0.4421% delta=0.3379pp
- turnover<=1: N=193 ROI=-0.4443% delta=0.3357pp
- turnover<=2: N=285 ROI=-0.7762% delta=0.0038pp
- vol>=50k: N=359 ROI=-0.78% delta=0.0pp
- liq>=100k: N=232 ROI=-0.8005% delta=-0.0205pp
- liq>=100k & vol>=50k: N=232 ROI=-0.8005% delta=-0.0205pp
- tx>=100: N=328 ROI=-0.882% delta=-0.102pp
- vol>=25k: N=330 ROI=-0.9026% delta=-0.1226pp
- liq>=75k: N=286 ROI=-0.999% delta=-0.219pp

## Missed-star scan
- Candidates: 1165
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 71, 'LIQ_LT_15K': 1047, 'VOL_LT_15K': 723, 'TX_LT_50': 588}

Research only; validate prospectively before changing production gates.
