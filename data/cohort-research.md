# Wallet500 Cohort Research

Generated: 2026-08-31T05:23:12.103247+00:00
Source snapshot: 2026-08-31T05:23:10.955344+00:00

## Baseline
- N=92 ROI=-20.5139% P/L=$-18.872804

## Best post-hoc counterfactuals (min 5 retained)
- liq>=250k & vol>=100k: N=35 ROI=-3.4363% delta=17.0776pp
- liq>=250k: N=46 ROI=-3.6754% delta=16.8385pp
- liq>=500k: N=30 ROI=-5.0488% delta=15.4651pp
- liq>=100k: N=68 ROI=-9.2402% delta=11.2737pp
- turnover<=1: N=58 ROI=-9.4722% delta=11.0417pp
- liq>=100k & vol>=50k: N=57 ROI=-9.9666% delta=10.5473pp
- liq>=100k & tx>=250: N=48 ROI=-10.5446% delta=9.9693pp
- tx>=500: N=38 ROI=-16.6228% delta=3.8911pp
- liq>=75k: N=79 ROI=-18.22% delta=2.2939pp
- vol>=100k: N=55 ROI=-19.5687% delta=0.9452pp

## Missed-star scan
- Candidates: 484
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 35, 'LIQ_LT_50K': 427, 'VOL_LT_15K': 313, 'TX_LT_50': 261}

Research only; validate prospectively before changing production gates.
