# Wallet500 Cohort Research

Generated: 2026-09-22T02:06:03.561810+00:00
Source snapshot: 2026-09-22T01:59:32.674924+00:00

## Baseline
- N=359 ROI=-0.7349% P/L=$-2.638404

## Best post-hoc counterfactuals (min 5 retained)
- turnover<=1: N=193 ROI=-0.3606% delta=0.3743pp
- liq>=250k: N=128 ROI=-0.3864% delta=0.3485pp
- liq>=500k: N=174 ROI=-0.4421% delta=0.2928pp
- turnover<=2: N=285 ROI=-0.7195% delta=0.0154pp
- liq>=100k: N=232 ROI=-0.7309% delta=0.004pp
- liq>=100k & vol>=50k: N=232 ROI=-0.7309% delta=0.004pp
- vol>=50k: N=359 ROI=-0.7349% delta=0.0pp
- tx>=100: N=328 ROI=-0.8327% delta=-0.0978pp
- vol>=25k: N=330 ROI=-0.8536% delta=-0.1187pp
- liq>=75k: N=286 ROI=-0.9425% delta=-0.2076pp

## Missed-star scan
- Candidates: 1165
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 71, 'LIQ_LT_15K': 1047, 'VOL_LT_15K': 723, 'TX_LT_50': 588}

Research only; validate prospectively before changing production gates.
