# Wallet500 Cohort Research

Generated: 2026-08-31T03:35:23.802119+00:00
Source snapshot: 2026-08-31T03:35:22.382481+00:00

## Baseline
- N=79 ROI=-20.7502% P/L=$-16.392672

## Best post-hoc counterfactuals (min 5 retained)
- liq>=250k & vol>=100k: N=33 ROI=-4.2845% delta=16.4657pp
- liq>=250k: N=42 ROI=-5.0233% delta=15.7269pp
- liq>=500k: N=29 ROI=-6.7529% delta=13.9973pp
- liq>=100k: N=60 ROI=-9.3972% delta=11.353pp
- liq>=100k & tx>=250: N=41 ROI=-9.9755% delta=10.7747pp
- liq>=100k & vol>=50k: N=53 ROI=-10.0222% delta=10.728pp
- turnover<=1: N=54 ROI=-10.5843% delta=10.1659pp
- vol>=100k: N=47 ROI=-16.9567% delta=3.7935pp
- liq>=75k: N=68 ROI=-17.3541% delta=3.3961pp
- tx>=500: N=35 ROI=-18.3869% delta=2.3633pp

## Missed-star scan
- Candidates: 455
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 36, 'LIQ_LT_50K': 400, 'VOL_LT_15K': 296, 'TX_LT_50': 246}

Research only; validate prospectively before changing production gates.
