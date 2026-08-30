# Wallet500 Cohort Research

Generated: 2026-08-30T21:40:47.103738+00:00
Source snapshot: 2026-08-30T21:40:45.901967+00:00

## Baseline
- N=56 ROI=-12.1437% P/L=$-6.800483

## Best post-hoc counterfactuals (min 5 retained)
- liq>=250k: N=35 ROI=-1.8386% delta=10.3051pp
- liq>=250k & vol>=100k: N=27 ROI=-2.4887% delta=9.655pp
- liq>=500k: N=25 ROI=-2.6309% delta=9.5128pp
- turnover<=1: N=42 ROI=-2.7699% delta=9.3738pp
- liq>=100k: N=45 ROI=-6.0138% delta=6.1299pp
- liq>=100k & vol>=50k: N=39 ROI=-6.2032% delta=5.9405pp
- liq>=100k & tx>=250: N=29 ROI=-7.4031% delta=4.7406pp
- liq>=75k: N=48 ROI=-7.4052% delta=4.7385pp
- turnover<=2: N=48 ROI=-8.6247% delta=3.519pp
- vol>=100k: N=35 ROI=-9.6193% delta=2.5244pp

## Missed-star scan
- Candidates: 405
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 31, 'LIQ_LT_50K': 353, 'VOL_LT_15K': 263, 'TX_LT_50': 223}

Research only; validate prospectively before changing production gates.
