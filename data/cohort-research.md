# Wallet500 Cohort Research

Generated: 2026-09-01T14:49:40.442385+00:00
Source snapshot: 2026-09-01T14:49:38.094974+00:00

## Baseline
- N=267 ROI=955.4164% P/L=$2550.961869

## Best post-hoc counterfactuals (min 5 retained)
- liq>=500k: N=62 ROI=4184.6055% delta=3229.1891pp
- liq>=250k & vol>=100k: N=89 ROI=2935.7043% delta=1980.2879pp
- liq>=250k: N=111 ROI=2354.5337% delta=1399.1173pp
- tx>=500: N=130 ROI=1996.9705% delta=1041.5541pp
- liq>=100k & tx>=250: N=145 ROI=1790.0486% delta=834.6322pp
- turnover<=1: N=148 ROI=1749.3258% delta=793.9094pp
- liq>=100k & vol>=50k: N=153 ROI=1695.5207% delta=740.1043pp
- vol>=100k: N=158 ROI=1627.3282% delta=671.9118pp
- liq>=100k: N=187 ROI=1387.1063% delta=431.6899pp
- vol>=50k: N=206 ROI=1238.7743% delta=283.3579pp

## Missed-star scan
- Candidates: 943
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 62, 'LIQ_LT_50K': 840, 'VOL_LT_15K': 590, 'TX_LT_50': 474}

Research only; validate prospectively before changing production gates.
