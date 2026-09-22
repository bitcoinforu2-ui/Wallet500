# Wallet500 Cohort Research

Generated: 2026-09-22T15:40:50.372470+00:00
Source snapshot: 2026-09-22T15:34:15.885294+00:00

## Baseline
- N=359 ROI=-0.7456% P/L=$-2.676772

## Best post-hoc counterfactuals (min 5 retained)
- turnover<=1: N=193 ROI=-0.3804% delta=0.3652pp
- liq>=250k: N=128 ROI=-0.3864% delta=0.3592pp
- liq>=500k: N=174 ROI=-0.4421% delta=0.3035pp
- turnover<=2: N=285 ROI=-0.733% delta=0.0126pp
- vol>=50k: N=359 ROI=-0.7456% delta=0.0pp
- liq>=100k: N=232 ROI=-0.7474% delta=-0.0018pp
- liq>=100k & vol>=50k: N=232 ROI=-0.7474% delta=-0.0018pp
- tx>=100: N=328 ROI=-0.8444% delta=-0.0988pp
- vol>=25k: N=330 ROI=-0.8652% delta=-0.1196pp
- liq>=75k: N=286 ROI=-0.9559% delta=-0.2103pp

## Missed-star scan
- Candidates: 1165
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 71, 'LIQ_LT_15K': 1047, 'VOL_LT_15K': 723, 'TX_LT_50': 588}

Research only; validate prospectively before changing production gates.
