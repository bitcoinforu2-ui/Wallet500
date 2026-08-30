# Wallet500 Cohort Research

Generated: 2026-08-30T20:10:19.148511+00:00
Source snapshot: 2026-08-30T20:10:17.863320+00:00

## Baseline
- N=50 ROI=-10.6074% P/L=$-5.303715

## Best post-hoc counterfactuals (min 5 retained)
- liq>=250k: N=33 ROI=-1.5186% delta=9.0888pp
- turnover<=1: N=37 ROI=-1.7585% delta=8.8489pp
- liq>=500k: N=25 ROI=-2.2702% delta=8.3372pp
- liq>=250k & vol>=100k: N=25 ROI=-2.4723% delta=8.1351pp
- liq>=100k: N=41 ROI=-5.5029% delta=5.1045pp
- liq>=100k & vol>=50k: N=35 ROI=-6.5611% delta=4.0463pp
- liq>=75k: N=44 ROI=-7.0556% delta=3.5518pp
- turnover<=2: N=42 ROI=-7.2408% delta=3.3666pp
- pre-runup<=10%: N=26 ROI=-8.4019% delta=2.2055pp
- liq>=100k & tx>=250: N=25 ROI=-8.5089% delta=2.0985pp

## Missed-star scan
- Candidates: 387
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 30, 'LIQ_LT_50K': 336, 'VOL_LT_15K': 251, 'TX_LT_50': 212}

Research only; validate prospectively before changing production gates.
