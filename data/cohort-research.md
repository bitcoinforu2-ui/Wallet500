# Wallet500 Cohort Research

Generated: 2026-08-31T09:35:03.411894+00:00
Source snapshot: 2026-08-31T09:35:01.839156+00:00

## Baseline
- N=112 ROI=-21.5268% P/L=$-24.110062

## Best post-hoc counterfactuals (min 5 retained)
- liq>=250k: N=50 ROI=-4.3233% delta=17.2035pp
- liq>=250k & vol>=100k: N=39 ROI=-4.7335% delta=16.7933pp
- turnover<=1: N=69 ROI=-6.0683% delta=15.4585pp
- liq>=500k: N=32 ROI=-6.7211% delta=14.8057pp
- liq>=100k: N=78 ROI=-9.2564% delta=12.2704pp
- liq>=100k & vol>=50k: N=64 ROI=-11.192% delta=10.3348pp
- liq>=100k & tx>=250: N=57 ROI=-12.045% delta=9.4818pp
- tx>=500: N=49 ROI=-14.8068% delta=6.72pp
- liq>=75k: N=93 ROI=-18.7749% delta=2.7519pp
- turnover<=2: N=94 ROI=-22.1442% delta=-0.6174pp

## Missed-star scan
- Candidates: 534
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 41, 'LIQ_LT_50K': 470, 'VOL_LT_15K': 340, 'TX_LT_50': 280}

Research only; validate prospectively before changing production gates.
