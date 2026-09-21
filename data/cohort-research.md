# Wallet500 Cohort Research

Generated: 2026-09-21T08:42:57.343379+00:00
Source snapshot: 2026-09-21T08:36:34.612698+00:00

## Baseline
- N=359 ROI=-0.7391% P/L=$-2.653506

## Best post-hoc counterfactuals (min 5 retained)
- turnover<=1: N=193 ROI=-0.3684% delta=0.3707pp
- liq>=250k: N=128 ROI=-0.3864% delta=0.3527pp
- liq>=500k: N=174 ROI=-0.4421% delta=0.297pp
- turnover<=2: N=285 ROI=-0.7248% delta=0.0143pp
- liq>=100k: N=232 ROI=-0.7374% delta=0.0017pp
- liq>=100k & vol>=50k: N=232 ROI=-0.7374% delta=0.0017pp
- vol>=50k: N=359 ROI=-0.7391% delta=0.0pp
- tx>=100: N=328 ROI=-0.8374% delta=-0.0983pp
- vol>=25k: N=330 ROI=-0.8582% delta=-0.1191pp
- liq>=75k: N=286 ROI=-0.9478% delta=-0.2087pp

## Missed-star scan
- Candidates: 1165
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 71, 'LIQ_LT_15K': 1047, 'VOL_LT_15K': 723, 'TX_LT_50': 588}

Research only; validate prospectively before changing production gates.
