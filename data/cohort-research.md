# Wallet500 Cohort Research

Generated: 2026-09-20T22:52:28.246285+00:00
Source snapshot: 2026-09-20T22:45:51.993063+00:00

## Baseline
- N=359 ROI=-0.7441% P/L=$-2.671466

## Best post-hoc counterfactuals (min 5 retained)
- turnover<=1: N=193 ROI=-0.3777% delta=0.3664pp
- liq>=250k: N=128 ROI=-0.3864% delta=0.3577pp
- liq>=500k: N=174 ROI=-0.4421% delta=0.302pp
- turnover<=2: N=285 ROI=-0.7311% delta=0.013pp
- vol>=50k: N=359 ROI=-0.7441% delta=0.0pp
- liq>=100k: N=232 ROI=-0.7451% delta=-0.001pp
- liq>=100k & vol>=50k: N=232 ROI=-0.7451% delta=-0.001pp
- tx>=100: N=328 ROI=-0.8428% delta=-0.0987pp
- vol>=25k: N=330 ROI=-0.8636% delta=-0.1195pp
- liq>=75k: N=286 ROI=-0.954% delta=-0.2099pp

## Missed-star scan
- Candidates: 1165
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 71, 'LIQ_LT_15K': 1047, 'VOL_LT_15K': 723, 'TX_LT_50': 588}

Research only; validate prospectively before changing production gates.
