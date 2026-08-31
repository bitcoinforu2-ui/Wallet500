# Wallet500 Cohort Research

Generated: 2026-08-31T23:35:08.377973+00:00
Source snapshot: 2026-08-31T23:35:06.959927+00:00

## Baseline
- N=166 ROI=-19.2169% P/L=$-31.900102

## Best post-hoc counterfactuals (min 5 retained)
- liq>=250k & vol>=100k: N=55 ROI=4.7665% delta=23.9834pp
- liq>=250k: N=72 ROI=4.6522% delta=23.8691pp
- liq>=500k: N=41 ROI=-4.3294% delta=14.8875pp
- turnover<=1: N=97 ROI=-6.7798% delta=12.4371pp
- liq>=100k: N=121 ROI=-7.4591% delta=11.7578pp
- liq>=100k & tx>=250: N=90 ROI=-8.6183% delta=10.5986pp
- liq>=100k & vol>=50k: N=99 ROI=-9.6029% delta=9.614pp
- tx>=500: N=76 ROI=-9.9696% delta=9.2473pp
- liq>=75k: N=140 ROI=-15.8794% delta=3.3375pp
- vol>=25k: N=153 ROI=-21.14% delta=-1.9231pp

## Missed-star scan
- Candidates: 685
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 46, 'LIQ_LT_50K': 608, 'VOL_LT_15K': 436, 'TX_LT_50': 354}

Research only; validate prospectively before changing production gates.
