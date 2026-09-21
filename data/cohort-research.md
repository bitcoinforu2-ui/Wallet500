# Wallet500 Cohort Research

Generated: 2026-09-21T11:15:58.008244+00:00
Source snapshot: 2026-09-21T11:09:28.178538+00:00

## Baseline
- N=359 ROI=-0.7385% P/L=$-2.651057

## Best post-hoc counterfactuals (min 5 retained)
- turnover<=1: N=193 ROI=-0.3671% delta=0.3714pp
- liq>=250k: N=128 ROI=-0.3864% delta=0.3521pp
- liq>=500k: N=174 ROI=-0.4421% delta=0.2964pp
- turnover<=2: N=285 ROI=-0.724% delta=0.0145pp
- liq>=100k: N=232 ROI=-0.7363% delta=0.0022pp
- liq>=100k & vol>=50k: N=232 ROI=-0.7363% delta=0.0022pp
- vol>=50k: N=359 ROI=-0.7385% delta=0.0pp
- tx>=100: N=328 ROI=-0.8366% delta=-0.0981pp
- vol>=25k: N=330 ROI=-0.8574% delta=-0.1189pp
- liq>=75k: N=286 ROI=-0.9469% delta=-0.2084pp

## Missed-star scan
- Candidates: 1165
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 71, 'LIQ_LT_15K': 1047, 'VOL_LT_15K': 723, 'TX_LT_50': 588}

Research only; validate prospectively before changing production gates.
