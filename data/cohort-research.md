# Wallet500 Cohort Research

Generated: 2026-09-07T03:49:43.769121+00:00
Source snapshot: 2026-09-07T03:41:33.532794+00:00

## Baseline
- N=355 ROI=-0.762% P/L=$-2.704935

## Best post-hoc counterfactuals (min 5 retained)
- liq>=250k: N=128 ROI=-0.3864% delta=0.3756pp
- turnover<=1: N=192 ROI=-0.3971% delta=0.3649pp
- turnover<=2: N=281 ROI=-0.7534% delta=0.0086pp
- liq>=100k: N=232 ROI=-0.7595% delta=0.0025pp
- tx>=100: N=325 ROI=-0.8609% delta=-0.0989pp
- vol>=25k: N=328 ROI=-0.8791% delta=-0.1171pp
- liq>=75k: N=286 ROI=-0.9657% delta=-0.2037pp
- tx>=500: N=183 ROI=-1.006% delta=-0.244pp
- tx>=250: N=282 ROI=-1.0074% delta=-0.2454pp
- liq>=100k & tx>=250: N=182 ROI=-1.0429% delta=-0.2809pp

## Missed-star scan
- Candidates: 1165
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 76, 'LIQ_LT_50K': 1042, 'VOL_LT_15K': 718, 'TX_LT_50': 580}

Research only; validate prospectively before changing production gates.
