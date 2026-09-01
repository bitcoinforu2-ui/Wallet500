# Wallet500 Cohort Research

Generated: 2026-09-01T02:10:30.595317+00:00
Source snapshot: 2026-09-01T02:10:28.568386+00:00

## Baseline
- N=181 ROI=-18.8023% P/L=$-34.032178

## Best post-hoc counterfactuals (min 5 retained)
- liq>=250k & vol>=100k: N=62 ROI=3.5901% delta=22.3924pp
- liq>=250k: N=82 ROI=2.8688% delta=21.6711pp
- liq>=500k: N=48 ROI=-5.658% delta=13.1443pp
- turnover<=1: N=105 ROI=-6.6871% delta=12.1152pp
- liq>=100k: N=131 ROI=-7.6676% delta=11.1347pp
- liq>=100k & tx>=250: N=97 ROI=-9.2678% delta=9.5345pp
- liq>=100k & vol>=50k: N=107 ROI=-9.656% delta=9.1463pp
- tx>=500: N=82 ROI=-10.0191% delta=8.7832pp
- liq>=75k: N=154 ROI=-15.6776% delta=3.1247pp
- tx>=100: N=158 ROI=-20.4451% delta=-1.6428pp

## Missed-star scan
- Candidates: 715
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 46, 'LIQ_LT_50K': 634, 'VOL_LT_15K': 448, 'TX_LT_50': 357}

Research only; validate prospectively before changing production gates.
