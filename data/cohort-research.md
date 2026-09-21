# Wallet500 Cohort Research

Generated: 2026-09-21T18:45:58.550546+00:00
Source snapshot: 2026-09-21T18:39:31.216085+00:00

## Baseline
- N=359 ROI=-0.7297% P/L=$-2.619629

## Best post-hoc counterfactuals (min 5 retained)
- turnover<=1: N=193 ROI=-0.3508% delta=0.3789pp
- liq>=250k: N=128 ROI=-0.3864% delta=0.3433pp
- liq>=500k: N=174 ROI=-0.4421% delta=0.2876pp
- turnover<=2: N=285 ROI=-0.7129% delta=0.0168pp
- liq>=100k: N=232 ROI=-0.7228% delta=0.0069pp
- liq>=100k & vol>=50k: N=232 ROI=-0.7228% delta=0.0069pp
- vol>=50k: N=359 ROI=-0.7297% delta=0.0pp
- tx>=100: N=328 ROI=-0.827% delta=-0.0973pp
- vol>=25k: N=330 ROI=-0.8479% delta=-0.1182pp
- liq>=75k: N=286 ROI=-0.9359% delta=-0.2062pp

## Missed-star scan
- Candidates: 1165
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 71, 'LIQ_LT_15K': 1047, 'VOL_LT_15K': 723, 'TX_LT_50': 588}

Research only; validate prospectively before changing production gates.
