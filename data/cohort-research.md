# Wallet500 Cohort Research

Generated: 2026-10-09T09:21:44.291028+00:00
Source snapshot: 2026-10-09T09:14:46.686863+00:00

## Baseline
- N=359 ROI=-0.8377% P/L=$-3.007384

## Best post-hoc counterfactuals (min 5 retained)
- liq>=250k: N=128 ROI=-0.3864% delta=0.4513pp
- liq>=500k: N=174 ROI=-0.4421% delta=0.3956pp
- turnover<=1: N=193 ROI=-0.5517% delta=0.286pp
- vol>=50k: N=359 ROI=-0.8377% delta=0.0pp
- turnover<=2: N=285 ROI=-0.849% delta=-0.0113pp
- liq>=100k: N=232 ROI=-0.8899% delta=-0.0522pp
- liq>=100k & vol>=50k: N=232 ROI=-0.8899% delta=-0.0522pp
- tx>=100: N=328 ROI=-0.9452% delta=-0.1075pp
- vol>=25k: N=330 ROI=-0.9654% delta=-0.1277pp
- liq>=75k: N=286 ROI=-1.0715% delta=-0.2338pp

## Missed-star scan
- Candidates: 1165
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 71, 'LIQ_LT_15K': 1047, 'VOL_LT_15K': 723, 'TX_LT_50': 588}

Research only; validate prospectively before changing production gates.
