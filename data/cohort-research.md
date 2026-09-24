# Wallet500 Cohort Research

Generated: 2026-09-24T05:29:18.652815+00:00
Source snapshot: 2026-09-24T05:22:50.695531+00:00

## Baseline
- N=359 ROI=-0.7597% P/L=$-2.727384

## Best post-hoc counterfactuals (min 5 retained)
- liq>=250k: N=128 ROI=-0.3864% delta=0.3733pp
- turnover<=1: N=193 ROI=-0.4067% delta=0.353pp
- liq>=500k: N=174 ROI=-0.4421% delta=0.3176pp
- turnover<=2: N=285 ROI=-0.7507% delta=0.009pp
- vol>=50k: N=359 ROI=-0.7597% delta=0.0pp
- liq>=100k: N=232 ROI=-0.7692% delta=-0.0095pp
- liq>=100k & vol>=50k: N=232 ROI=-0.7692% delta=-0.0095pp
- tx>=100: N=328 ROI=-0.8599% delta=-0.1002pp
- vol>=25k: N=330 ROI=-0.8806% delta=-0.1209pp
- liq>=75k: N=286 ROI=-0.9736% delta=-0.2139pp

## Missed-star scan
- Candidates: 1165
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 71, 'LIQ_LT_15K': 1047, 'VOL_LT_15K': 723, 'TX_LT_50': 588}

Research only; validate prospectively before changing production gates.
