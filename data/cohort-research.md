# Wallet500 Cohort Research

Generated: 2026-09-16T11:26:58.762669+00:00
Source snapshot: 2026-09-16T11:20:22.510696+00:00

## Baseline
- N=359 ROI=-0.8134% P/L=$-2.920037

## Best post-hoc counterfactuals (min 5 retained)
- liq>=250k: N=128 ROI=-0.3864% delta=0.427pp
- liq>=500k: N=174 ROI=-0.4421% delta=0.3713pp
- turnover<=1: N=193 ROI=-0.5065% delta=0.3069pp
- vol>=50k: N=359 ROI=-0.8134% delta=0.0pp
- turnover<=2: N=285 ROI=-0.8183% delta=-0.0049pp
- liq>=100k: N=232 ROI=-0.8523% delta=-0.0389pp
- liq>=100k & vol>=50k: N=232 ROI=-0.8523% delta=-0.0389pp
- tx>=100: N=328 ROI=-0.9186% delta=-0.1052pp
- vol>=25k: N=330 ROI=-0.9389% delta=-0.1255pp
- liq>=75k: N=286 ROI=-1.041% delta=-0.2276pp

## Missed-star scan
- Candidates: 1165
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 71, 'LIQ_LT_15K': 1047, 'VOL_LT_15K': 723, 'TX_LT_50': 588}

Research only; validate prospectively before changing production gates.
