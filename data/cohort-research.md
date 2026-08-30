# Wallet500 Cohort Research

Generated: 2026-08-30T21:21:54.959777+00:00
Source snapshot: 2026-08-30T21:21:53.708754+00:00

## Baseline
- N=53 ROI=-11.1249% P/L=$-5.896196

## Best post-hoc counterfactuals (min 5 retained)
- liq>=250k: N=34 ROI=-1.5611% delta=9.5638pp
- liq>=500k: N=25 ROI=-2.3888% delta=8.7361pp
- liq>=250k & vol>=100k: N=26 ROI=-2.4246% delta=8.7003pp
- turnover<=1: N=39 ROI=-2.454% delta=8.6709pp
- liq>=100k: N=43 ROI=-5.78% delta=5.3449pp
- liq>=100k & vol>=50k: N=37 ROI=-6.374% delta=4.7509pp
- liq>=75k: N=46 ROI=-7.2472% delta=3.8777pp
- turnover<=2: N=45 ROI=-7.2674% delta=3.8575pp
- liq>=100k & tx>=250: N=27 ROI=-7.8441% delta=3.2808pp
- pre-runup<=10%: N=27 ROI=-8.7555% delta=2.3694pp

## Missed-star scan
- Candidates: 397
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 31, 'LIQ_LT_50K': 345, 'VOL_LT_15K': 256, 'TX_LT_50': 220}

Research only; validate prospectively before changing production gates.
