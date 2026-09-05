# Wallet500 Cohort Research

Generated: 2026-09-05T02:12:27.571764+00:00
Source snapshot: 2026-09-05T02:04:37.382138+00:00

## Baseline
- N=355 ROI=-0.7245% P/L=$-2.571874

## Best post-hoc counterfactuals (min 5 retained)
- turnover<=1: N=192 ROI=-0.3278% delta=0.3967pp
- liq>=250k: N=128 ROI=-0.3864% delta=0.3381pp
- liq>=100k: N=232 ROI=-0.7022% delta=0.0223pp
- turnover<=2: N=281 ROI=-0.7061% delta=0.0184pp
- tx>=100: N=325 ROI=-0.82% delta=-0.0955pp
- vol>=25k: N=328 ROI=-0.8385% delta=-0.114pp
- liq>=75k: N=286 ROI=-0.9192% delta=-0.1947pp
- tx>=500: N=183 ROI=-0.9333% delta=-0.2088pp
- tx>=250: N=282 ROI=-0.9602% delta=-0.2357pp
- liq>=100k & tx>=250: N=182 ROI=-0.9698% delta=-0.2453pp

## Missed-star scan
- Candidates: 1165
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 76, 'LIQ_LT_50K': 1042, 'VOL_LT_15K': 718, 'TX_LT_50': 580}

Research only; validate prospectively before changing production gates.
