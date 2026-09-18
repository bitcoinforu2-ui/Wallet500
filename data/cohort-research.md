# Wallet500 Cohort Research

Generated: 2026-09-18T17:51:34.360886+00:00
Source snapshot: 2026-09-18T17:44:51.038360+00:00

## Baseline
- N=359 ROI=-0.7989% P/L=$-2.8682

## Best post-hoc counterfactuals (min 5 retained)
- liq>=250k: N=128 ROI=-0.3864% delta=0.4125pp
- liq>=500k: N=174 ROI=-0.4421% delta=0.3568pp
- turnover<=1: N=193 ROI=-0.4796% delta=0.3193pp
- vol>=50k: N=359 ROI=-0.7989% delta=0.0pp
- turnover<=2: N=285 ROI=-0.8002% delta=-0.0013pp
- liq>=100k: N=232 ROI=-0.8299% delta=-0.031pp
- liq>=100k & vol>=50k: N=232 ROI=-0.8299% delta=-0.031pp
- tx>=100: N=328 ROI=-0.9028% delta=-0.1039pp
- vol>=25k: N=330 ROI=-0.9232% delta=-0.1243pp
- liq>=75k: N=286 ROI=-1.0228% delta=-0.2239pp

## Missed-star scan
- Candidates: 1165
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 71, 'LIQ_LT_15K': 1047, 'VOL_LT_15K': 723, 'TX_LT_50': 588}

Research only; validate prospectively before changing production gates.
