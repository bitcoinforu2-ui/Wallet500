# Wallet500 Cohort Research

Generated: 2026-09-26T23:58:41.957311+00:00
Source snapshot: 2026-09-26T23:52:04.353550+00:00

## Baseline
- N=359 ROI=-0.7817% P/L=$-2.806159

## Best post-hoc counterfactuals (min 5 retained)
- liq>=250k: N=128 ROI=-0.3864% delta=0.3953pp
- liq>=500k: N=174 ROI=-0.4421% delta=0.3396pp
- turnover<=1: N=193 ROI=-0.4475% delta=0.3342pp
- turnover<=2: N=285 ROI=-0.7784% delta=0.0033pp
- vol>=50k: N=359 ROI=-0.7817% delta=0.0pp
- liq>=100k: N=232 ROI=-0.8032% delta=-0.0215pp
- liq>=100k & vol>=50k: N=232 ROI=-0.8032% delta=-0.0215pp
- tx>=100: N=328 ROI=-0.8839% delta=-0.1022pp
- vol>=25k: N=330 ROI=-0.9044% delta=-0.1227pp
- liq>=75k: N=286 ROI=-1.0011% delta=-0.2194pp

## Missed-star scan
- Candidates: 1165
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 71, 'LIQ_LT_15K': 1047, 'VOL_LT_15K': 723, 'TX_LT_50': 588}

Research only; validate prospectively before changing production gates.
