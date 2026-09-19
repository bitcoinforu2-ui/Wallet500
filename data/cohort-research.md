# Wallet500 Cohort Research

Generated: 2026-09-19T01:52:39.295485+00:00
Source snapshot: 2026-09-19T01:46:28.228669+00:00

## Baseline
- N=359 ROI=-0.787% P/L=$-2.825343

## Best post-hoc counterfactuals (min 5 retained)
- liq>=250k: N=128 ROI=-0.3864% delta=0.4006pp
- liq>=500k: N=174 ROI=-0.4421% delta=0.3449pp
- turnover<=1: N=193 ROI=-0.4574% delta=0.3296pp
- turnover<=2: N=285 ROI=-0.7851% delta=0.0019pp
- vol>=50k: N=359 ROI=-0.787% delta=0.0pp
- liq>=100k: N=232 ROI=-0.8114% delta=-0.0244pp
- liq>=100k & vol>=50k: N=232 ROI=-0.8114% delta=-0.0244pp
- tx>=100: N=328 ROI=-0.8897% delta=-0.1027pp
- vol>=25k: N=330 ROI=-0.9103% delta=-0.1233pp
- liq>=75k: N=286 ROI=-1.0078% delta=-0.2208pp

## Missed-star scan
- Candidates: 1165
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 71, 'LIQ_LT_15K': 1047, 'VOL_LT_15K': 723, 'TX_LT_50': 588}

Research only; validate prospectively before changing production gates.
