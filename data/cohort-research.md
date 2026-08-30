# Wallet500 Cohort Research

Generated: 2026-08-30T23:10:23.267264+00:00
Source snapshot: 2026-08-30T23:10:21.870995+00:00

## Baseline
- N=66 ROI=-15.617% P/L=$-10.307216

## Best post-hoc counterfactuals (min 5 retained)
- liq>=250k: N=39 ROI=-2.5976% delta=13.0194pp
- liq>=250k & vol>=100k: N=31 ROI=-3.1368% delta=12.4802pp
- liq>=500k: N=27 ROI=-3.7031% delta=11.9139pp
- turnover<=1: N=46 ROI=-5.6206% delta=9.9964pp
- liq>=100k: N=51 ROI=-6.3655% delta=9.2515pp
- liq>=100k & vol>=50k: N=45 ROI=-6.3827% delta=9.2343pp
- liq>=100k & tx>=250: N=33 ROI=-7.2405% delta=8.3765pp
- liq>=75k: N=56 ROI=-10.8834% delta=4.7336pp
- vol>=100k: N=41 ROI=-11.6202% delta=3.9968pp
- tx>=500: N=29 ROI=-11.8408% delta=3.7762pp

## Missed-star scan
- Candidates: 424
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 30, 'LIQ_LT_50K': 374, 'VOL_LT_15K': 277, 'TX_LT_50': 239}

Research only; validate prospectively before changing production gates.
