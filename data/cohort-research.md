# Wallet500 Cohort Research

Generated: 2026-09-23T05:55:40.169854+00:00
Source snapshot: 2026-09-23T05:48:47.143168+00:00

## Baseline
- N=359 ROI=-0.7477% P/L=$-2.684119

## Best post-hoc counterfactuals (min 5 retained)
- turnover<=1: N=193 ROI=-0.3842% delta=0.3635pp
- liq>=250k: N=128 ROI=-0.3864% delta=0.3613pp
- liq>=500k: N=174 ROI=-0.4421% delta=0.3056pp
- turnover<=2: N=285 ROI=-0.7356% delta=0.0121pp
- vol>=50k: N=359 ROI=-0.7477% delta=0.0pp
- liq>=100k: N=232 ROI=-0.7506% delta=-0.0029pp
- liq>=100k & vol>=50k: N=232 ROI=-0.7506% delta=-0.0029pp
- tx>=100: N=328 ROI=-0.8467% delta=-0.099pp
- vol>=25k: N=330 ROI=-0.8675% delta=-0.1198pp
- liq>=75k: N=286 ROI=-0.9585% delta=-0.2108pp

## Missed-star scan
- Candidates: 1165
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 71, 'LIQ_LT_15K': 1047, 'VOL_LT_15K': 723, 'TX_LT_50': 588}

Research only; validate prospectively before changing production gates.
