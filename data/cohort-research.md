# Wallet500 Cohort Research

Generated: 2026-08-31T14:37:56.418107+00:00
Source snapshot: 2026-08-31T14:37:54.664730+00:00

## Baseline
- N=131 ROI=-20.8722% P/L=$-27.342574

## Best post-hoc counterfactuals (min 5 retained)
- liq>=250k & vol>=100k: N=46 ROI=-0.6557% delta=20.2165pp
- liq>=250k: N=59 ROI=-1.0764% delta=19.7958pp
- liq>=500k: N=39 ROI=-5.9024% delta=14.9698pp
- turnover<=1: N=77 ROI=-6.1139% delta=14.7583pp
- liq>=100k: N=96 ROI=-9.2251% delta=11.6471pp
- liq>=100k & vol>=50k: N=81 ROI=-10.2659% delta=10.6063pp
- liq>=100k & tx>=250: N=71 ROI=-10.6386% delta=10.2336pp
- tx>=500: N=60 ROI=-13.0001% delta=7.8721pp
- liq>=75k: N=111 ROI=-17.0047% delta=3.8675pp
- vol>=25k: N=123 ROI=-22.3241% delta=-1.4519pp

## Missed-star scan
- Candidates: 600
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 44, 'LIQ_LT_50K': 531, 'VOL_LT_15K': 384, 'TX_LT_50': 317}

Research only; validate prospectively before changing production gates.
