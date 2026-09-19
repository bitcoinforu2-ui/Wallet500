# Wallet500 Cohort Research

Generated: 2026-09-19T15:51:34.115489+00:00
Source snapshot: 2026-09-19T15:45:11.735881+00:00

## Baseline
- N=359 ROI=-0.7208% P/L=$-2.587792

## Best post-hoc counterfactuals (min 5 retained)
- turnover<=1: N=193 ROI=-0.3343% delta=0.3865pp
- liq>=250k: N=128 ROI=-0.3864% delta=0.3344pp
- liq>=500k: N=174 ROI=-0.4421% delta=0.2787pp
- turnover<=2: N=285 ROI=-0.7018% delta=0.019pp
- liq>=100k: N=232 ROI=-0.7091% delta=0.0117pp
- liq>=100k & vol>=50k: N=232 ROI=-0.7091% delta=0.0117pp
- vol>=50k: N=359 ROI=-0.7208% delta=0.0pp
- tx>=100: N=328 ROI=-0.8173% delta=-0.0965pp
- vol>=25k: N=330 ROI=-0.8383% delta=-0.1175pp
- liq>=75k: N=286 ROI=-0.9248% delta=-0.204pp

## Missed-star scan
- Candidates: 1165
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 71, 'LIQ_LT_15K': 1047, 'VOL_LT_15K': 723, 'TX_LT_50': 588}

Research only; validate prospectively before changing production gates.
