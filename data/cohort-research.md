# Wallet500 Cohort Research

Generated: 2026-09-21T16:34:19.457283+00:00
Source snapshot: 2026-09-21T16:27:36.171373+00:00

## Baseline
- N=359 ROI=-0.7308% P/L=$-2.62371

## Best post-hoc counterfactuals (min 5 retained)
- turnover<=1: N=193 ROI=-0.353% delta=0.3778pp
- liq>=250k: N=128 ROI=-0.3864% delta=0.3444pp
- liq>=500k: N=174 ROI=-0.4421% delta=0.2887pp
- turnover<=2: N=285 ROI=-0.7144% delta=0.0164pp
- liq>=100k: N=232 ROI=-0.7245% delta=0.0063pp
- liq>=100k & vol>=50k: N=232 ROI=-0.7245% delta=0.0063pp
- vol>=50k: N=359 ROI=-0.7308% delta=0.0pp
- tx>=100: N=328 ROI=-0.8283% delta=-0.0975pp
- vol>=25k: N=330 ROI=-0.8492% delta=-0.1184pp
- liq>=75k: N=286 ROI=-0.9373% delta=-0.2065pp

## Missed-star scan
- Candidates: 1165
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 71, 'LIQ_LT_15K': 1047, 'VOL_LT_15K': 723, 'TX_LT_50': 588}

Research only; validate prospectively before changing production gates.
