# Wallet500 Cohort Research

Generated: 2026-09-19T00:57:29.900997+00:00
Source snapshot: 2026-09-19T00:50:54.057458+00:00

## Baseline
- N=359 ROI=-0.7894% P/L=$-2.833915

## Best post-hoc counterfactuals (min 5 retained)
- liq>=250k: N=128 ROI=-0.3864% delta=0.403pp
- liq>=500k: N=174 ROI=-0.4421% delta=0.3473pp
- turnover<=1: N=193 ROI=-0.4619% delta=0.3275pp
- turnover<=2: N=285 ROI=-0.7881% delta=0.0013pp
- vol>=50k: N=359 ROI=-0.7894% delta=0.0pp
- liq>=100k: N=232 ROI=-0.8151% delta=-0.0257pp
- liq>=100k & vol>=50k: N=232 ROI=-0.8151% delta=-0.0257pp
- tx>=100: N=328 ROI=-0.8924% delta=-0.103pp
- vol>=25k: N=330 ROI=-0.9128% delta=-0.1234pp
- liq>=75k: N=286 ROI=-1.0108% delta=-0.2214pp

## Missed-star scan
- Candidates: 1165
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 71, 'LIQ_LT_15K': 1047, 'VOL_LT_15K': 723, 'TX_LT_50': 588}

Research only; validate prospectively before changing production gates.
