# Wallet500 Cohort Research

Generated: 2026-09-25T01:07:45.531735+00:00
Source snapshot: 2026-09-25T01:00:53.564479+00:00

## Baseline
- N=359 ROI=-0.7652% P/L=$-2.746976

## Best post-hoc counterfactuals (min 5 retained)
- liq>=250k: N=128 ROI=-0.3864% delta=0.3788pp
- turnover<=1: N=193 ROI=-0.4168% delta=0.3484pp
- liq>=500k: N=174 ROI=-0.4421% delta=0.3231pp
- turnover<=2: N=285 ROI=-0.7576% delta=0.0076pp
- vol>=50k: N=359 ROI=-0.7652% delta=0.0pp
- liq>=100k: N=232 ROI=-0.7777% delta=-0.0125pp
- liq>=100k & vol>=50k: N=232 ROI=-0.7777% delta=-0.0125pp
- tx>=100: N=328 ROI=-0.8658% delta=-0.1006pp
- vol>=25k: N=330 ROI=-0.8865% delta=-0.1213pp
- liq>=75k: N=286 ROI=-0.9804% delta=-0.2152pp

## Missed-star scan
- Candidates: 1165
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 71, 'LIQ_LT_15K': 1047, 'VOL_LT_15K': 723, 'TX_LT_50': 588}

Research only; validate prospectively before changing production gates.
