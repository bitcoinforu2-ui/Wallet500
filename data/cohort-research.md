# Wallet500 Cohort Research

Generated: 2026-08-31T18:20:57.821957+00:00
Source snapshot: 2026-08-31T18:20:56.098542+00:00

## Baseline
- N=146 ROI=-17.957% P/L=$-26.217246

## Best post-hoc counterfactuals (min 5 retained)
- liq>=250k & vol>=100k: N=50 ROI=6.224% delta=24.181pp
- liq>=250k: N=63 ROI=4.375% delta=22.332pp
- liq>=500k: N=39 ROI=-5.9382% delta=12.0188pp
- turnover<=1: N=86 ROI=-6.221% delta=11.736pp
- liq>=100k: N=104 ROI=-6.4258% delta=11.5312pp
- liq>=100k & vol>=50k: N=88 ROI=-6.914% delta=11.043pp
- liq>=100k & tx>=250: N=77 ROI=-6.9721% delta=10.9849pp
- tx>=500: N=66 ROI=-7.6251% delta=10.3319pp
- liq>=75k: N=121 ROI=-14.2482% delta=3.7088pp
- vol>=100k: N=86 ROI=-18.9317% delta=-0.9747pp

## Missed-star scan
- Candidates: 631
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 45, 'LIQ_LT_50K': 559, 'VOL_LT_15K': 401, 'TX_LT_50': 333}

Research only; validate prospectively before changing production gates.
