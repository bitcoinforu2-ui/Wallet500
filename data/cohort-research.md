# Wallet500 Cohort Research

Generated: 2026-09-01T03:26:23.894507+00:00
Source snapshot: 2026-09-01T03:26:22.455376+00:00

## Baseline
- N=187 ROI=-19.4978% P/L=$-36.460892

## Best post-hoc counterfactuals (min 5 retained)
- liq>=250k & vol>=100k: N=64 ROI=3.7217% delta=23.2195pp
- liq>=250k: N=85 ROI=2.9941% delta=22.4919pp
- liq>=500k: N=49 ROI=-5.1344% delta=14.3634pp
- turnover<=1: N=107 ROI=-6.641% delta=12.8568pp
- liq>=100k: N=134 ROI=-7.6879% delta=11.8099pp
- liq>=100k & tx>=250: N=99 ROI=-9.0469% delta=10.4509pp
- liq>=100k & vol>=50k: N=109 ROI=-9.5161% delta=9.9817pp
- tx>=500: N=84 ROI=-10.2121% delta=9.2857pp
- liq>=75k: N=158 ROI=-16.1498% delta=3.348pp
- vol>=100k: N=110 ROI=-20.3418% delta=-0.844pp

## Missed-star scan
- Candidates: 732
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 45, 'LIQ_LT_50K': 652, 'VOL_LT_15K': 452, 'TX_LT_50': 366}

Research only; validate prospectively before changing production gates.
