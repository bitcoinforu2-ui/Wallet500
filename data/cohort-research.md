# Wallet500 Cohort Research

Generated: 2026-09-22T23:25:42.423020+00:00
Source snapshot: 2026-09-22T23:19:02.172076+00:00

## Baseline
- N=359 ROI=-0.7496% P/L=$-2.691057

## Best post-hoc counterfactuals (min 5 retained)
- liq>=250k: N=128 ROI=-0.3864% delta=0.3632pp
- turnover<=1: N=193 ROI=-0.3878% delta=0.3618pp
- liq>=500k: N=174 ROI=-0.4421% delta=0.3075pp
- turnover<=2: N=285 ROI=-0.738% delta=0.0116pp
- vol>=50k: N=359 ROI=-0.7496% delta=0.0pp
- liq>=100k: N=232 ROI=-0.7536% delta=-0.004pp
- liq>=100k & vol>=50k: N=232 ROI=-0.7536% delta=-0.004pp
- tx>=100: N=328 ROI=-0.8488% delta=-0.0992pp
- vol>=25k: N=330 ROI=-0.8696% delta=-0.12pp
- liq>=75k: N=286 ROI=-0.9609% delta=-0.2113pp

## Missed-star scan
- Candidates: 1165
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 71, 'LIQ_LT_15K': 1047, 'VOL_LT_15K': 723, 'TX_LT_50': 588}

Research only; validate prospectively before changing production gates.
