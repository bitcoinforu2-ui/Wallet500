# Wallet500 Cohort Research

Generated: 2026-08-31T04:47:07.723234+00:00
Source snapshot: 2026-08-31T04:47:06.643925+00:00

## Baseline
- N=85 ROI=-21.4788% P/L=$-18.256994

## Best post-hoc counterfactuals (min 5 retained)
- liq>=250k & vol>=100k: N=34 ROI=-3.7265% delta=17.7523pp
- liq>=250k: N=44 ROI=-4.2071% delta=17.2717pp
- liq>=500k: N=30 ROI=-5.6096% delta=15.8692pp
- liq>=100k: N=63 ROI=-8.9212% delta=12.5576pp
- liq>=100k & vol>=50k: N=55 ROI=-9.3832% delta=12.0956pp
- turnover<=1: N=55 ROI=-9.9167% delta=11.5621pp
- liq>=100k & tx>=250: N=44 ROI=-10.0528% delta=11.426pp
- tx>=500: N=37 ROI=-18.1391% delta=3.3397pp
- liq>=75k: N=74 ROI=-18.5128% delta=2.966pp
- vol>=100k: N=52 ROI=-19.676% delta=1.8028pp

## Missed-star scan
- Candidates: 471
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 34, 'LIQ_LT_50K': 417, 'VOL_LT_15K': 303, 'TX_LT_50': 255}

Research only; validate prospectively before changing production gates.
