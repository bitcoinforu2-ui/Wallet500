# Wallet500 Cohort Research

Generated: 2026-09-04T09:22:53.920281+00:00
Source snapshot: 2026-09-04T09:22:51.156324+00:00

## Baseline
- N=355 ROI=-0.7256% P/L=$-2.575955

## Best post-hoc counterfactuals (min 5 retained)
- turnover<=1: N=192 ROI=-0.3299% delta=0.3957pp
- liq>=250k: N=128 ROI=-0.3864% delta=0.3392pp
- liq>=100k: N=232 ROI=-0.704% delta=0.0216pp
- turnover<=2: N=281 ROI=-0.7075% delta=0.0181pp
- tx>=100: N=325 ROI=-0.8212% delta=-0.0956pp
- vol>=25k: N=328 ROI=-0.8398% delta=-0.1142pp
- liq>=75k: N=286 ROI=-0.9207% delta=-0.1951pp
- tx>=500: N=183 ROI=-0.9355% delta=-0.2099pp
- tx>=250: N=282 ROI=-0.9617% delta=-0.2361pp
- liq>=100k & tx>=250: N=182 ROI=-0.9721% delta=-0.2465pp

## Missed-star scan
- Candidates: 1165
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 76, 'LIQ_LT_50K': 1042, 'VOL_LT_15K': 718, 'TX_LT_50': 580}

Research only; validate prospectively before changing production gates.
