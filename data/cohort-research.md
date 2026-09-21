# Wallet500 Cohort Research

Generated: 2026-09-21T15:39:38.249946+00:00
Source snapshot: 2026-09-21T15:32:53.588804+00:00

## Baseline
- N=359 ROI=-0.7338% P/L=$-2.634323

## Best post-hoc counterfactuals (min 5 retained)
- turnover<=1: N=193 ROI=-0.3584% delta=0.3754pp
- liq>=250k: N=128 ROI=-0.3864% delta=0.3474pp
- liq>=500k: N=174 ROI=-0.4421% delta=0.2917pp
- turnover<=2: N=285 ROI=-0.7181% delta=0.0157pp
- liq>=100k: N=232 ROI=-0.7291% delta=0.0047pp
- liq>=100k & vol>=50k: N=232 ROI=-0.7291% delta=0.0047pp
- vol>=50k: N=359 ROI=-0.7338% delta=0.0pp
- tx>=100: N=328 ROI=-0.8315% delta=-0.0977pp
- vol>=25k: N=330 ROI=-0.8524% delta=-0.1186pp
- liq>=75k: N=286 ROI=-0.9411% delta=-0.2073pp

## Missed-star scan
- Candidates: 1165
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 71, 'LIQ_LT_15K': 1047, 'VOL_LT_15K': 723, 'TX_LT_50': 588}

Research only; validate prospectively before changing production gates.
