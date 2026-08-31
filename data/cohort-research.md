# Wallet500 Cohort Research

Generated: 2026-08-31T20:34:16.401123+00:00
Source snapshot: 2026-08-31T20:34:14.883417+00:00

## Baseline
- N=159 ROI=-18.0698% P/L=$-28.730958

## Best post-hoc counterfactuals (min 5 retained)
- liq>=250k & vol>=100k: N=53 ROI=5.3635% delta=23.4333pp
- liq>=250k: N=70 ROI=4.8135% delta=22.8833pp
- liq>=500k: N=41 ROI=-4.252% delta=13.8178pp
- turnover<=1: N=94 ROI=-6.1895% delta=11.8803pp
- liq>=100k: N=115 ROI=-6.3017% delta=11.7681pp
- liq>=100k & tx>=250: N=85 ROI=-6.7925% delta=11.2773pp
- tx>=500: N=72 ROI=-7.2224% delta=10.8474pp
- liq>=100k & vol>=50k: N=95 ROI=-7.8461% delta=10.2237pp
- liq>=75k: N=133 ROI=-14.1565% delta=3.9133pp
- vol>=25k: N=146 ROI=-19.6608% delta=-1.591pp

## Missed-star scan
- Candidates: 655
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 46, 'LIQ_LT_50K': 581, 'VOL_LT_15K': 408, 'TX_LT_50': 336}

Research only; validate prospectively before changing production gates.
