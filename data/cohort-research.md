# Wallet500 Cohort Research

Generated: 2026-09-25T02:28:57.715393+00:00
Source snapshot: 2026-09-25T02:22:35.447137+00:00

## Baseline
- N=359 ROI=-0.7651% P/L=$-2.746568

## Best post-hoc counterfactuals (min 5 retained)
- liq>=250k: N=128 ROI=-0.3864% delta=0.3787pp
- turnover<=1: N=193 ROI=-0.4166% delta=0.3485pp
- liq>=500k: N=174 ROI=-0.4421% delta=0.323pp
- turnover<=2: N=285 ROI=-0.7575% delta=0.0076pp
- vol>=50k: N=359 ROI=-0.7651% delta=0.0pp
- liq>=100k: N=232 ROI=-0.7775% delta=-0.0124pp
- liq>=100k & vol>=50k: N=232 ROI=-0.7775% delta=-0.0124pp
- tx>=100: N=328 ROI=-0.8657% delta=-0.1006pp
- vol>=25k: N=330 ROI=-0.8864% delta=-0.1213pp
- liq>=75k: N=286 ROI=-0.9803% delta=-0.2152pp

## Missed-star scan
- Candidates: 1165
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 71, 'LIQ_LT_15K': 1047, 'VOL_LT_15K': 723, 'TX_LT_50': 588}

Research only; validate prospectively before changing production gates.
