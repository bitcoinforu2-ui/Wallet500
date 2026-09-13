# Wallet500 Cohort Research

Generated: 2026-09-13T21:50:20.645917+00:00
Source snapshot: 2026-09-13T21:44:21.790944+00:00

## Baseline
- N=359 ROI=-0.8093% P/L=$-2.905343

## Best post-hoc counterfactuals (min 5 retained)
- liq>=250k: N=128 ROI=-0.3864% delta=0.4229pp
- liq>=500k: N=174 ROI=-0.4421% delta=0.3672pp
- turnover<=1: N=193 ROI=-0.4989% delta=0.3104pp
- vol>=50k: N=359 ROI=-0.8093% delta=0.0pp
- turnover<=2: N=285 ROI=-0.8132% delta=-0.0039pp
- liq>=100k: N=232 ROI=-0.8459% delta=-0.0366pp
- liq>=100k & vol>=50k: N=232 ROI=-0.8459% delta=-0.0366pp
- tx>=100: N=328 ROI=-0.9141% delta=-0.1048pp
- vol>=25k: N=330 ROI=-0.9345% delta=-0.1252pp
- liq>=75k: N=286 ROI=-1.0358% delta=-0.2265pp

## Missed-star scan
- Candidates: 1165
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 71, 'LIQ_LT_15K': 1047, 'VOL_LT_15K': 723, 'TX_LT_50': 588}

Research only; validate prospectively before changing production gates.
