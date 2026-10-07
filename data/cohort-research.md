# Wallet500 Cohort Research

Generated: 2026-10-07T13:58:38.825777+00:00
Source snapshot: 2026-10-07T13:52:06.125918+00:00

## Baseline
- N=359 ROI=-0.8311% P/L=$-2.98371

## Best post-hoc counterfactuals (min 5 retained)
- liq>=250k: N=128 ROI=-0.3864% delta=0.4447pp
- liq>=500k: N=174 ROI=-0.4421% delta=0.389pp
- turnover<=1: N=193 ROI=-0.5395% delta=0.2916pp
- vol>=50k: N=359 ROI=-0.8311% delta=0.0pp
- turnover<=2: N=285 ROI=-0.8407% delta=-0.0096pp
- liq>=100k: N=232 ROI=-0.8797% delta=-0.0486pp
- liq>=100k & vol>=50k: N=232 ROI=-0.8797% delta=-0.0486pp
- tx>=100: N=328 ROI=-0.938% delta=-0.1069pp
- vol>=25k: N=330 ROI=-0.9582% delta=-0.1271pp
- liq>=75k: N=286 ROI=-1.0632% delta=-0.2321pp

## Missed-star scan
- Candidates: 1165
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 71, 'LIQ_LT_15K': 1047, 'VOL_LT_15K': 723, 'TX_LT_50': 588}

Research only; validate prospectively before changing production gates.
