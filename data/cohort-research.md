# Wallet500 Cohort Research

Generated: 2026-09-16T07:41:45.606428+00:00
Source snapshot: 2026-09-16T07:35:04.353695+00:00

## Baseline
- N=359 ROI=-0.812% P/L=$-2.915139

## Best post-hoc counterfactuals (min 5 retained)
- liq>=250k: N=128 ROI=-0.3864% delta=0.4256pp
- liq>=500k: N=174 ROI=-0.4421% delta=0.3699pp
- turnover<=1: N=193 ROI=-0.5039% delta=0.3081pp
- vol>=50k: N=359 ROI=-0.812% delta=0.0pp
- turnover<=2: N=285 ROI=-0.8166% delta=-0.0046pp
- liq>=100k: N=232 ROI=-0.8502% delta=-0.0382pp
- liq>=100k & vol>=50k: N=232 ROI=-0.8502% delta=-0.0382pp
- tx>=100: N=328 ROI=-0.9171% delta=-0.1051pp
- vol>=25k: N=330 ROI=-0.9375% delta=-0.1255pp
- liq>=75k: N=286 ROI=-1.0392% delta=-0.2272pp

## Missed-star scan
- Candidates: 1165
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 71, 'LIQ_LT_15K': 1047, 'VOL_LT_15K': 723, 'TX_LT_50': 588}

Research only; validate prospectively before changing production gates.
