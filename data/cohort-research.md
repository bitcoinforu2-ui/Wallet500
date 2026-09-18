# Wallet500 Cohort Research

Generated: 2026-09-18T08:27:43.030949+00:00
Source snapshot: 2026-09-18T08:21:12.256180+00:00

## Baseline
- N=359 ROI=-0.807% P/L=$-2.89718

## Best post-hoc counterfactuals (min 5 retained)
- liq>=250k: N=128 ROI=-0.3864% delta=0.4206pp
- liq>=500k: N=174 ROI=-0.4421% delta=0.3649pp
- turnover<=1: N=193 ROI=-0.4946% delta=0.3124pp
- vol>=50k: N=359 ROI=-0.807% delta=0.0pp
- turnover<=2: N=285 ROI=-0.8103% delta=-0.0033pp
- liq>=100k: N=232 ROI=-0.8424% delta=-0.0354pp
- liq>=100k & vol>=50k: N=232 ROI=-0.8424% delta=-0.0354pp
- tx>=100: N=328 ROI=-0.9116% delta=-0.1046pp
- vol>=25k: N=330 ROI=-0.932% delta=-0.125pp
- liq>=75k: N=286 ROI=-1.033% delta=-0.226pp

## Missed-star scan
- Candidates: 1165
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 71, 'LIQ_LT_15K': 1047, 'VOL_LT_15K': 723, 'TX_LT_50': 588}

Research only; validate prospectively before changing production gates.
