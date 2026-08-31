# Wallet500 Cohort Research

Generated: 2026-08-31T13:07:53.266727+00:00
Source snapshot: 2026-08-31T13:07:51.549557+00:00

## Baseline
- N=125 ROI=-22.4077% P/L=$-28.009656

## Best post-hoc counterfactuals (min 5 retained)
- liq>=250k: N=55 ROI=-4.0769% delta=18.3308pp
- liq>=250k & vol>=100k: N=43 ROI=-4.667% delta=17.7407pp
- turnover<=1: N=74 ROI=-5.9917% delta=16.416pp
- liq>=500k: N=35 ROI=-6.3616% delta=16.0461pp
- liq>=100k: N=90 ROI=-11.0078% delta=11.3999pp
- liq>=100k & vol>=50k: N=76 ROI=-12.5425% delta=9.8652pp
- liq>=100k & tx>=250: N=67 ROI=-13.5623% delta=8.8454pp
- tx>=500: N=56 ROI=-15.935% delta=6.4727pp
- liq>=75k: N=105 ROI=-18.9606% delta=3.4471pp
- turnover<=2: N=100 ROI=-22.5014% delta=-0.0937pp

## Missed-star scan
- Candidates: 585
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 42, 'LIQ_LT_50K': 517, 'VOL_LT_15K': 374, 'TX_LT_50': 308}

Research only; validate prospectively before changing production gates.
