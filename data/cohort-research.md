# Wallet500 Cohort Research

Generated: 2026-09-26T06:12:42.532989+00:00
Source snapshot: 2026-09-26T06:06:11.850168+00:00

## Baseline
- N=359 ROI=-0.7806% P/L=$-2.802486

## Best post-hoc counterfactuals (min 5 retained)
- liq>=250k: N=128 ROI=-0.3864% delta=0.3942pp
- liq>=500k: N=174 ROI=-0.4421% delta=0.3385pp
- turnover<=1: N=193 ROI=-0.4456% delta=0.335pp
- turnover<=2: N=285 ROI=-0.7771% delta=0.0035pp
- vol>=50k: N=359 ROI=-0.7806% delta=0.0pp
- liq>=100k: N=232 ROI=-0.8016% delta=-0.021pp
- liq>=100k & vol>=50k: N=232 ROI=-0.8016% delta=-0.021pp
- tx>=100: N=328 ROI=-0.8828% delta=-0.1022pp
- vol>=25k: N=330 ROI=-0.9033% delta=-0.1227pp
- liq>=75k: N=286 ROI=-0.9999% delta=-0.2193pp

## Missed-star scan
- Candidates: 1165
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 71, 'LIQ_LT_15K': 1047, 'VOL_LT_15K': 723, 'TX_LT_50': 588}

Research only; validate prospectively before changing production gates.
