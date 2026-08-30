# Wallet500 Cohort Research

Generated: 2026-08-30T22:33:52.715603+00:00
Source snapshot: 2026-08-30T22:33:51.439534+00:00

## Baseline
- N=63 ROI=-12.4608% P/L=$-7.850302

## Best post-hoc counterfactuals (min 5 retained)
- liq>=250k: N=38 ROI=-2.3258% delta=10.135pp
- liq>=250k & vol>=100k: N=30 ROI=-2.9081% delta=9.5527pp
- liq>=500k: N=26 ROI=-3.3484% delta=9.1124pp
- turnover<=1: N=44 ROI=-4.9236% delta=7.5372pp
- liq>=100k: N=48 ROI=-5.6745% delta=6.7863pp
- liq>=100k & vol>=50k: N=42 ROI=-5.9214% delta=6.5394pp
- liq>=100k & tx>=250: N=31 ROI=-7.1481% delta=5.3127pp
- liq>=75k: N=53 ROI=-8.6265% delta=3.8343pp
- vol>=100k: N=40 ROI=-8.9381% delta=3.5227pp
- turnover<=2: N=53 ROI=-9.8559% delta=2.6049pp

## Missed-star scan
- Candidates: 417
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 31, 'LIQ_LT_50K': 366, 'VOL_LT_15K': 273, 'TX_LT_50': 231}

Research only; validate prospectively before changing production gates.
