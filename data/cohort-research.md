# Wallet500 Cohort Research

Generated: 2026-09-20T01:51:44.038207+00:00
Source snapshot: 2026-09-20T01:45:22.162100+00:00

## Baseline
- N=359 ROI=-1.0083% P/L=$-3.619629

## Best post-hoc counterfactuals (min 5 retained)
- turnover<=1: N=193 ROI=-0.3508% delta=0.6575pp
- liq>=250k: N=128 ROI=-0.3864% delta=0.6219pp
- liq>=500k: N=174 ROI=-0.4421% delta=0.5662pp
- liq>=100k: N=232 ROI=-0.7228% delta=0.2855pp
- liq>=100k & vol>=50k: N=232 ROI=-0.7228% delta=0.2855pp
- liq>=75k: N=286 ROI=-0.9359% delta=0.0724pp
- tx>=500: N=184 ROI=-0.9542% delta=0.0541pp
- tx>=250: N=283 ROI=-0.9737% delta=0.0346pp
- liq>=100k & tx>=250: N=182 ROI=-0.9961% delta=0.0122pp
- vol>=50k: N=359 ROI=-1.0083% delta=0.0pp

## Missed-star scan
- Candidates: 1165
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 71, 'LIQ_LT_15K': 1047, 'VOL_LT_15K': 723, 'TX_LT_50': 588}

Research only; validate prospectively before changing production gates.
