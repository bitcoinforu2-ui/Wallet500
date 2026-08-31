# Wallet500 Cohort Research

Generated: 2026-08-31T07:45:14.136393+00:00
Source snapshot: 2026-08-31T07:45:12.564798+00:00

## Baseline
- N=103 ROI=-22.1482% P/L=$-22.812617

## Best post-hoc counterfactuals (min 5 retained)
- liq>=250k: N=50 ROI=-3.9218% delta=18.2264pp
- liq>=250k & vol>=100k: N=39 ROI=-4.2826% delta=17.8656pp
- liq>=500k: N=32 ROI=-6.0924% delta=16.0558pp
- turnover<=1: N=64 ROI=-6.4461% delta=15.7021pp
- liq>=100k: N=75 ROI=-9.6042% delta=12.544pp
- liq>=100k & vol>=50k: N=63 ROI=-11.3125% delta=10.8357pp
- liq>=100k & tx>=250: N=55 ROI=-12.0713% delta=10.0769pp
- tx>=500: N=43 ROI=-16.018% delta=6.1302pp
- liq>=75k: N=88 ROI=-18.5357% delta=3.6125pp
- turnover<=2: N=86 ROI=-22.8088% delta=-0.6606pp

## Missed-star scan
- Candidates: 501
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 36, 'LIQ_LT_50K': 442, 'VOL_LT_15K': 324, 'TX_LT_50': 271}

Research only; validate prospectively before changing production gates.
