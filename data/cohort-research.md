# Wallet500 Cohort Research

Generated: 2026-09-05T03:14:21.670047+00:00
Source snapshot: 2026-09-05T03:06:26.861720+00:00

## Baseline
- N=355 ROI=-0.7236% P/L=$-2.568608

## Best post-hoc counterfactuals (min 5 retained)
- turnover<=1: N=192 ROI=-0.3261% delta=0.3975pp
- liq>=250k: N=128 ROI=-0.3864% delta=0.3372pp
- liq>=100k: N=232 ROI=-0.7008% delta=0.0228pp
- turnover<=2: N=281 ROI=-0.7049% delta=0.0187pp
- tx>=100: N=325 ROI=-0.819% delta=-0.0954pp
- vol>=25k: N=328 ROI=-0.8375% delta=-0.1139pp
- liq>=75k: N=286 ROI=-0.9181% delta=-0.1945pp
- tx>=500: N=183 ROI=-0.9315% delta=-0.2079pp
- tx>=250: N=282 ROI=-0.9591% delta=-0.2355pp
- liq>=100k & tx>=250: N=182 ROI=-0.968% delta=-0.2444pp

## Missed-star scan
- Candidates: 1165
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 76, 'LIQ_LT_50K': 1042, 'VOL_LT_15K': 718, 'TX_LT_50': 580}

Research only; validate prospectively before changing production gates.
