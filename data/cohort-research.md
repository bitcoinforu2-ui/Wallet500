# Wallet500 Cohort Research

Generated: 2026-09-25T05:09:29.708615+00:00
Source snapshot: 2026-09-25T05:02:06.755428+00:00

## Baseline
- N=359 ROI=-0.7751% P/L=$-2.782486

## Best post-hoc counterfactuals (min 5 retained)
- liq>=250k: N=128 ROI=-0.3864% delta=0.3887pp
- turnover<=1: N=193 ROI=-0.4352% delta=0.3399pp
- liq>=500k: N=174 ROI=-0.4421% delta=0.333pp
- turnover<=2: N=285 ROI=-0.7701% delta=0.005pp
- vol>=50k: N=359 ROI=-0.7751% delta=0.0pp
- liq>=100k: N=232 ROI=-0.793% delta=-0.0179pp
- liq>=100k & vol>=50k: N=232 ROI=-0.793% delta=-0.0179pp
- tx>=100: N=328 ROI=-0.8767% delta=-0.1016pp
- vol>=25k: N=330 ROI=-0.8973% delta=-0.1222pp
- liq>=75k: N=286 ROI=-0.9929% delta=-0.2178pp

## Missed-star scan
- Candidates: 1165
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 71, 'LIQ_LT_15K': 1047, 'VOL_LT_15K': 723, 'TX_LT_50': 588}

Research only; validate prospectively before changing production gates.
