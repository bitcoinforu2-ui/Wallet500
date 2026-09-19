# Wallet500 Cohort Research

Generated: 2026-09-19T12:31:05.643057+00:00
Source snapshot: 2026-09-19T12:24:42.918507+00:00

## Baseline
- N=359 ROI=-0.7008% P/L=$-2.515955

## Best post-hoc counterfactuals (min 5 retained)
- turnover<=1: N=193 ROI=-0.2971% delta=0.4037pp
- liq>=250k: N=128 ROI=-0.3864% delta=0.3144pp
- liq>=500k: N=174 ROI=-0.4421% delta=0.2587pp
- turnover<=2: N=285 ROI=-0.6766% delta=0.0242pp
- liq>=100k: N=232 ROI=-0.6781% delta=0.0227pp
- liq>=100k & vol>=50k: N=232 ROI=-0.6781% delta=0.0227pp
- vol>=50k: N=359 ROI=-0.7008% delta=0.0pp
- tx>=100: N=328 ROI=-0.7954% delta=-0.0946pp
- vol>=25k: N=330 ROI=-0.8165% delta=-0.1157pp
- tx>=500: N=184 ROI=-0.8979% delta=-0.1971pp

## Missed-star scan
- Candidates: 1165
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 71, 'LIQ_LT_15K': 1047, 'VOL_LT_15K': 723, 'TX_LT_50': 588}

Research only; validate prospectively before changing production gates.
