# Wallet500 Cohort Research

Generated: 2026-09-19T07:06:38.506500+00:00
Source snapshot: 2026-09-19T07:00:14.061018+00:00

## Baseline
- N=359 ROI=-0.7404% P/L=$-2.657996

## Best post-hoc counterfactuals (min 5 retained)
- turnover<=1: N=193 ROI=-0.3707% delta=0.3697pp
- liq>=250k: N=128 ROI=-0.3864% delta=0.354pp
- liq>=500k: N=174 ROI=-0.4421% delta=0.2983pp
- turnover<=2: N=285 ROI=-0.7264% delta=0.014pp
- liq>=100k: N=232 ROI=-0.7393% delta=0.0011pp
- liq>=100k & vol>=50k: N=232 ROI=-0.7393% delta=0.0011pp
- vol>=50k: N=359 ROI=-0.7404% delta=0.0pp
- tx>=100: N=328 ROI=-0.8387% delta=-0.0983pp
- vol>=25k: N=330 ROI=-0.8595% delta=-0.1191pp
- liq>=75k: N=286 ROI=-0.9493% delta=-0.2089pp

## Missed-star scan
- Candidates: 1165
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 71, 'LIQ_LT_15K': 1047, 'VOL_LT_15K': 723, 'TX_LT_50': 588}

Research only; validate prospectively before changing production gates.
