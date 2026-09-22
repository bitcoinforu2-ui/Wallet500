# Wallet500 Cohort Research

Generated: 2026-09-22T01:57:01.128158+00:00
Source snapshot: 2026-09-22T01:50:32.159022+00:00

## Baseline
- N=359 ROI=-0.7324% P/L=$-2.629425

## Best post-hoc counterfactuals (min 5 retained)
- turnover<=1: N=193 ROI=-0.3559% delta=0.3765pp
- liq>=250k: N=128 ROI=-0.3864% delta=0.346pp
- liq>=500k: N=174 ROI=-0.4421% delta=0.2903pp
- turnover<=2: N=285 ROI=-0.7164% delta=0.016pp
- liq>=100k: N=232 ROI=-0.727% delta=0.0054pp
- liq>=100k & vol>=50k: N=232 ROI=-0.727% delta=0.0054pp
- vol>=50k: N=359 ROI=-0.7324% delta=0.0pp
- tx>=100: N=328 ROI=-0.83% delta=-0.0976pp
- vol>=25k: N=330 ROI=-0.8509% delta=-0.1185pp
- liq>=75k: N=286 ROI=-0.9393% delta=-0.2069pp

## Missed-star scan
- Candidates: 1165
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 71, 'LIQ_LT_15K': 1047, 'VOL_LT_15K': 723, 'TX_LT_50': 588}

Research only; validate prospectively before changing production gates.
