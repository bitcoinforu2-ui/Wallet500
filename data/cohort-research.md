# Wallet500 Cohort Research

Generated: 2026-08-30T22:13:43.046449+00:00
Source snapshot: 2026-08-30T22:13:41.757111+00:00

## Baseline
- N=59 ROI=-11.4526% P/L=$-6.757012

## Best post-hoc counterfactuals (min 5 retained)
- liq>=250k: N=36 ROI=-2.0702% delta=9.3824pp
- liq>=250k & vol>=100k: N=28 ROI=-2.6801% delta=8.7725pp
- turnover<=1: N=43 ROI=-2.8291% delta=8.6235pp
- liq>=500k: N=25 ROI=-3.0454% delta=8.4072pp
- liq>=100k: N=46 ROI=-5.7888% delta=5.6638pp
- liq>=100k & vol>=50k: N=40 ROI=-5.8694% delta=5.5832pp
- liq>=100k & tx>=250: N=30 ROI=-6.8414% delta=4.6112pp
- liq>=75k: N=50 ROI=-7.0223% delta=4.4303pp
- turnover<=2: N=50 ROI=-8.4502% delta=3.0024pp
- vol>=100k: N=37 ROI=-8.9636% delta=2.489pp

## Missed-star scan
- Candidates: 408
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 31, 'LIQ_LT_50K': 357, 'VOL_LT_15K': 267, 'TX_LT_50': 226}

Research only; validate prospectively before changing production gates.
