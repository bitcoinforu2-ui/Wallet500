# Wallet500 Cohort Research

Generated: 2026-08-31T22:39:36.782397+00:00
Source snapshot: 2026-08-31T22:39:34.659728+00:00

## Baseline
- N=164 ROI=-18.9995% P/L=$-31.159254

## Best post-hoc counterfactuals (min 5 retained)
- liq>=250k & vol>=100k: N=54 ROI=5.4671% delta=24.4666pp
- liq>=250k: N=71 ROI=5.1627% delta=24.1622pp
- liq>=500k: N=41 ROI=-3.5227% delta=15.4768pp
- turnover<=1: N=96 ROI=-6.501% delta=12.4985pp
- liq>=100k: N=119 ROI=-7.4495% delta=11.55pp
- liq>=100k & tx>=250: N=88 ROI=-8.5702% delta=10.4293pp
- liq>=100k & vol>=50k: N=98 ROI=-9.397% delta=9.6025pp
- tx>=500: N=75 ROI=-9.4846% delta=9.5149pp
- liq>=75k: N=138 ROI=-15.7698% delta=3.2297pp
- vol>=25k: N=151 ROI=-20.7298% delta=-1.7303pp

## Missed-star scan
- Candidates: 671
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 45, 'LIQ_LT_50K': 596, 'VOL_LT_15K': 424, 'TX_LT_50': 343}

Research only; validate prospectively before changing production gates.
