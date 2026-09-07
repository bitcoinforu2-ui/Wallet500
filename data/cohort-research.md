# Wallet500 Cohort Research

Generated: 2026-09-07T13:24:42.706306+00:00
Source snapshot: 2026-09-07T13:16:15.918707+00:00

## Baseline
- N=355 ROI=-0.7615% P/L=$-2.703302

## Best post-hoc counterfactuals (min 5 retained)
- liq>=250k: N=128 ROI=-0.3864% delta=0.3751pp
- turnover<=1: N=192 ROI=-0.3962% delta=0.3653pp
- turnover<=2: N=281 ROI=-0.7529% delta=0.0086pp
- liq>=100k: N=232 ROI=-0.7588% delta=0.0027pp
- tx>=100: N=325 ROI=-0.8604% delta=-0.0989pp
- vol>=25k: N=328 ROI=-0.8786% delta=-0.1171pp
- liq>=75k: N=286 ROI=-0.9652% delta=-0.2037pp
- tx>=500: N=183 ROI=-1.0051% delta=-0.2436pp
- tx>=250: N=282 ROI=-1.0068% delta=-0.2453pp
- liq>=100k & tx>=250: N=182 ROI=-1.042% delta=-0.2805pp

## Missed-star scan
- Candidates: 1165
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 76, 'LIQ_LT_50K': 1042, 'VOL_LT_15K': 718, 'TX_LT_50': 580}

Research only; validate prospectively before changing production gates.
