# Wallet500 Cohort Research

Generated: 2026-09-24T01:26:42.269130+00:00
Source snapshot: 2026-09-24T01:20:26.245684+00:00

## Baseline
- N=359 ROI=-0.7563% P/L=$-2.715139

## Best post-hoc counterfactuals (min 5 retained)
- liq>=250k: N=128 ROI=-0.3864% delta=0.3699pp
- turnover<=1: N=193 ROI=-0.4003% delta=0.356pp
- liq>=500k: N=174 ROI=-0.4421% delta=0.3142pp
- turnover<=2: N=285 ROI=-0.7464% delta=0.0099pp
- vol>=50k: N=359 ROI=-0.7563% delta=0.0pp
- liq>=100k: N=232 ROI=-0.7639% delta=-0.0076pp
- liq>=100k & vol>=50k: N=232 ROI=-0.7639% delta=-0.0076pp
- tx>=100: N=328 ROI=-0.8561% delta=-0.0998pp
- vol>=25k: N=330 ROI=-0.8769% delta=-0.1206pp
- liq>=75k: N=286 ROI=-0.9693% delta=-0.213pp

## Missed-star scan
- Candidates: 1165
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 71, 'LIQ_LT_15K': 1047, 'VOL_LT_15K': 723, 'TX_LT_50': 588}

Research only; validate prospectively before changing production gates.
