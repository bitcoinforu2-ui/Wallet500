# Wallet500 Cohort Research

Generated: 2026-09-22T04:31:11.865285+00:00
Source snapshot: 2026-09-22T04:24:28.847520+00:00

## Baseline
- N=359 ROI=-0.7369% P/L=$-2.645343

## Best post-hoc counterfactuals (min 5 retained)
- turnover<=1: N=193 ROI=-0.3642% delta=0.3727pp
- liq>=250k: N=128 ROI=-0.3864% delta=0.3505pp
- liq>=500k: N=174 ROI=-0.4421% delta=0.2948pp
- turnover<=2: N=285 ROI=-0.722% delta=0.0149pp
- liq>=100k: N=232 ROI=-0.7339% delta=0.003pp
- liq>=100k & vol>=50k: N=232 ROI=-0.7339% delta=0.003pp
- vol>=50k: N=359 ROI=-0.7369% delta=0.0pp
- tx>=100: N=328 ROI=-0.8349% delta=-0.098pp
- vol>=25k: N=330 ROI=-0.8557% delta=-0.1188pp
- liq>=75k: N=286 ROI=-0.9449% delta=-0.208pp

## Missed-star scan
- Candidates: 1165
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 71, 'LIQ_LT_15K': 1047, 'VOL_LT_15K': 723, 'TX_LT_50': 588}

Research only; validate prospectively before changing production gates.
