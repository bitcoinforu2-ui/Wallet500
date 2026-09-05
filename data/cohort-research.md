# Wallet500 Cohort Research

Generated: 2026-09-05T06:14:08.033553+00:00
Source snapshot: 2026-09-05T06:06:00.499553+00:00

## Baseline
- N=355 ROI=-0.7241% P/L=$-2.570649

## Best post-hoc counterfactuals (min 5 retained)
- turnover<=1: N=192 ROI=-0.3272% delta=0.3969pp
- liq>=250k: N=128 ROI=-0.3864% delta=0.3377pp
- liq>=100k: N=232 ROI=-0.7017% delta=0.0224pp
- turnover<=2: N=281 ROI=-0.7057% delta=0.0184pp
- tx>=100: N=325 ROI=-0.8196% delta=-0.0955pp
- vol>=25k: N=328 ROI=-0.8382% delta=-0.1141pp
- liq>=75k: N=286 ROI=-0.9188% delta=-0.1947pp
- tx>=500: N=183 ROI=-0.9326% delta=-0.2085pp
- tx>=250: N=282 ROI=-0.9598% delta=-0.2357pp
- liq>=100k & tx>=250: N=182 ROI=-0.9691% delta=-0.245pp

## Missed-star scan
- Candidates: 1165
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 76, 'LIQ_LT_50K': 1042, 'VOL_LT_15K': 718, 'TX_LT_50': 580}

Research only; validate prospectively before changing production gates.
