# Wallet500 Cohort Research

Generated: 2026-08-31T06:14:50.003058+00:00
Source snapshot: 2026-08-31T06:14:48.094417+00:00

## Baseline
- N=97 ROI=-21.7502% P/L=$-21.097671

## Best post-hoc counterfactuals (min 5 retained)
- liq>=250k & vol>=100k: N=36 ROI=-3.6493% delta=18.1009pp
- liq>=250k: N=47 ROI=-3.9323% delta=17.8179pp
- liq>=500k: N=30 ROI=-5.4687% delta=16.2815pp
- turnover<=1: N=61 ROI=-7.2077% delta=14.5425pp
- liq>=100k: N=71 ROI=-10.5971% delta=11.1531pp
- liq>=100k & vol>=50k: N=59 ROI=-11.9555% delta=9.7947pp
- liq>=100k & tx>=250: N=51 ROI=-12.4968% delta=9.2534pp
- tx>=500: N=40 ROI=-16.5096% delta=5.2406pp
- liq>=75k: N=82 ROI=-19.021% delta=2.7292pp
- turnover<=2: N=81 ROI=-21.8858% delta=-0.1356pp

## Missed-star scan
- Candidates: 492
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 36, 'LIQ_LT_50K': 434, 'VOL_LT_15K': 317, 'TX_LT_50': 266}

Research only; validate prospectively before changing production gates.
