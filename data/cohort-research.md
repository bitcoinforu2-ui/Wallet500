# Wallet500 Cohort Research

Generated: 2026-09-19T09:38:40.770439+00:00
Source snapshot: 2026-09-19T09:32:16.036231+00:00

## Baseline
- N=359 ROI=-0.6985% P/L=$-2.507792

## Best post-hoc counterfactuals (min 5 retained)
- turnover<=1: N=193 ROI=-0.2929% delta=0.4056pp
- liq>=250k: N=128 ROI=-0.3864% delta=0.3121pp
- liq>=500k: N=174 ROI=-0.4421% delta=0.2564pp
- turnover<=2: N=285 ROI=-0.6737% delta=0.0248pp
- liq>=100k: N=232 ROI=-0.6746% delta=0.0239pp
- liq>=100k & vol>=50k: N=232 ROI=-0.6746% delta=0.0239pp
- vol>=50k: N=359 ROI=-0.6985% delta=0.0pp
- tx>=100: N=328 ROI=-0.7929% delta=-0.0944pp
- vol>=25k: N=330 ROI=-0.814% delta=-0.1155pp
- tx>=500: N=184 ROI=-0.8934% delta=-0.1949pp

## Missed-star scan
- Candidates: 1165
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 71, 'LIQ_LT_15K': 1047, 'VOL_LT_15K': 723, 'TX_LT_50': 588}

Research only; validate prospectively before changing production gates.
