# Wallet500 Cohort Research

Generated: 2026-09-19T01:39:08.304047+00:00
Source snapshot: 2026-09-19T01:32:35.889785+00:00

## Baseline
- N=359 ROI=-0.7876% P/L=$-2.827384

## Best post-hoc counterfactuals (min 5 retained)
- liq>=250k: N=128 ROI=-0.3864% delta=0.4012pp
- liq>=500k: N=174 ROI=-0.4421% delta=0.3455pp
- turnover<=1: N=193 ROI=-0.4585% delta=0.3291pp
- turnover<=2: N=285 ROI=-0.7858% delta=0.0018pp
- vol>=50k: N=359 ROI=-0.7876% delta=0.0pp
- liq>=100k: N=232 ROI=-0.8123% delta=-0.0247pp
- liq>=100k & vol>=50k: N=232 ROI=-0.8123% delta=-0.0247pp
- tx>=100: N=328 ROI=-0.8904% delta=-0.1028pp
- vol>=25k: N=330 ROI=-0.9109% delta=-0.1233pp
- liq>=75k: N=286 ROI=-1.0086% delta=-0.221pp

## Missed-star scan
- Candidates: 1165
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 71, 'LIQ_LT_15K': 1047, 'VOL_LT_15K': 723, 'TX_LT_50': 588}

Research only; validate prospectively before changing production gates.
