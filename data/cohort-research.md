# Wallet500 Cohort Research

Generated: 2026-08-31T18:06:17.568147+00:00
Source snapshot: 2026-08-31T18:06:15.672401+00:00

## Baseline
- N=143 ROI=-18.2202% P/L=$-26.054873

## Best post-hoc counterfactuals (min 5 retained)
- liq>=250k & vol>=100k: N=50 ROI=6.2342% delta=24.4544pp
- liq>=250k: N=63 ROI=4.6001% delta=22.8203pp
- liq>=500k: N=39 ROI=-5.5912% delta=12.629pp
- turnover<=1: N=84 ROI=-6.1279% delta=12.0923pp
- liq>=100k: N=103 ROI=-6.4411% delta=11.7791pp
- liq>=100k & vol>=50k: N=87 ROI=-7.0506% delta=11.1696pp
- liq>=100k & tx>=250: N=76 ROI=-7.0893% delta=11.1309pp
- tx>=500: N=66 ROI=-7.6288% delta=10.5914pp
- liq>=75k: N=119 ROI=-14.4951% delta=3.7251pp
- vol>=100k: N=85 ROI=-19.1565% delta=-0.9363pp

## Missed-star scan
- Candidates: 625
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 45, 'LIQ_LT_50K': 553, 'VOL_LT_15K': 397, 'TX_LT_50': 330}

Research only; validate prospectively before changing production gates.
