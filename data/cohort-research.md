# Wallet500 Cohort Research

Generated: 2026-09-04T15:15:40.045425+00:00
Source snapshot: 2026-09-04T15:07:28.219607+00:00

## Baseline
- N=355 ROI=-0.7317% P/L=$-2.597588

## Best post-hoc counterfactuals (min 5 retained)
- turnover<=1: N=192 ROI=-0.3412% delta=0.3905pp
- liq>=250k: N=128 ROI=-0.3864% delta=0.3453pp
- liq>=100k: N=232 ROI=-0.7133% delta=0.0184pp
- turnover<=2: N=281 ROI=-0.7152% delta=0.0165pp
- tx>=100: N=325 ROI=-0.8279% delta=-0.0962pp
- vol>=25k: N=328 ROI=-0.8464% delta=-0.1147pp
- liq>=75k: N=286 ROI=-0.9282% delta=-0.1965pp
- tx>=500: N=183 ROI=-0.9474% delta=-0.2157pp
- tx>=250: N=282 ROI=-0.9694% delta=-0.2377pp
- liq>=100k & tx>=250: N=182 ROI=-0.9839% delta=-0.2522pp

## Missed-star scan
- Candidates: 1165
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 76, 'LIQ_LT_50K': 1042, 'VOL_LT_15K': 718, 'TX_LT_50': 580}

Research only; validate prospectively before changing production gates.
