# Wallet500 Cohort Research

Generated: 2026-08-31T05:07:20.131285+00:00
Source snapshot: 2026-08-31T05:07:18.631928+00:00

## Baseline
- N=88 ROI=-21.8658% P/L=$-19.241894

## Best post-hoc counterfactuals (min 5 retained)
- liq>=250k & vol>=100k: N=35 ROI=-3.403% delta=18.4628pp
- liq>=250k: N=45 ROI=-3.9236% delta=17.9422pp
- liq>=500k: N=30 ROI=-5.2931% delta=16.5727pp
- turnover<=1: N=56 ROI=-9.8307% delta=12.0351pp
- liq>=100k: N=65 ROI=-10.3537% delta=11.5121pp
- liq>=100k & vol>=50k: N=56 ROI=-11.1018% delta=10.764pp
- liq>=100k & tx>=250: N=46 ROI=-11.698% delta=10.1678pp
- tx>=500: N=38 ROI=-17.2213% delta=4.6445pp
- liq>=75k: N=76 ROI=-19.4856% delta=2.3802pp
- vol>=100k: N=53 ROI=-20.8987% delta=0.9671pp

## Missed-star scan
- Candidates: 481
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 34, 'LIQ_LT_50K': 426, 'VOL_LT_15K': 307, 'TX_LT_50': 258}

Research only; validate prospectively before changing production gates.
