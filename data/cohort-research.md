# Wallet500 Cohort Research

Generated: 2026-09-21T04:51:28.011678+00:00
Source snapshot: 2026-09-21T04:44:52.180559+00:00

## Baseline
- N=359 ROI=-0.7389% P/L=$-2.65269

## Best post-hoc counterfactuals (min 5 retained)
- turnover<=1: N=193 ROI=-0.368% delta=0.3709pp
- liq>=250k: N=128 ROI=-0.3864% delta=0.3525pp
- liq>=500k: N=174 ROI=-0.4421% delta=0.2968pp
- turnover<=2: N=285 ROI=-0.7245% delta=0.0144pp
- liq>=100k: N=232 ROI=-0.737% delta=0.0019pp
- liq>=100k & vol>=50k: N=232 ROI=-0.737% delta=0.0019pp
- vol>=50k: N=359 ROI=-0.7389% delta=0.0pp
- tx>=100: N=328 ROI=-0.8371% delta=-0.0982pp
- vol>=25k: N=330 ROI=-0.8579% delta=-0.119pp
- liq>=75k: N=286 ROI=-0.9475% delta=-0.2086pp

## Missed-star scan
- Candidates: 1165
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 71, 'LIQ_LT_15K': 1047, 'VOL_LT_15K': 723, 'TX_LT_50': 588}

Research only; validate prospectively before changing production gates.
