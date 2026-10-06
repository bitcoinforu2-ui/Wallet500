# Wallet500 Cohort Research

Generated: 2026-10-06T16:11:22.780752+00:00
Source snapshot: 2026-10-06T16:04:39.426651+00:00

## Baseline
- N=359 ROI=-0.8074% P/L=$-2.898404

## Best post-hoc counterfactuals (min 5 retained)
- liq>=250k: N=128 ROI=-0.3864% delta=0.421pp
- liq>=500k: N=174 ROI=-0.4421% delta=0.3653pp
- turnover<=1: N=193 ROI=-0.4953% delta=0.3121pp
- vol>=50k: N=359 ROI=-0.8074% delta=0.0pp
- turnover<=2: N=285 ROI=-0.8108% delta=-0.0034pp
- liq>=100k: N=232 ROI=-0.8429% delta=-0.0355pp
- liq>=100k & vol>=50k: N=232 ROI=-0.8429% delta=-0.0355pp
- tx>=100: N=328 ROI=-0.912% delta=-0.1046pp
- vol>=25k: N=330 ROI=-0.9324% delta=-0.125pp
- liq>=75k: N=286 ROI=-1.0334% delta=-0.226pp

## Missed-star scan
- Candidates: 1165
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 71, 'LIQ_LT_15K': 1047, 'VOL_LT_15K': 723, 'TX_LT_50': 588}

Research only; validate prospectively before changing production gates.
