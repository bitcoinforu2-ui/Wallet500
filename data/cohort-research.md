# Wallet500 Cohort Research

Generated: 2026-09-01T12:01:42.348536+00:00
Source snapshot: 2026-09-01T12:01:39.902300+00:00

## Baseline
- N=256 ROI=998.3142% P/L=$2555.684366

## Best post-hoc counterfactuals (min 5 retained)
- liq>=500k: N=61 ROI=4254.8152% delta=3256.501pp
- liq>=250k & vol>=100k: N=87 ROI=3004.0569% delta=2005.7427pp
- liq>=250k: N=109 ROI=2398.5731% delta=1400.2589pp
- tx>=500: N=123 ROI=2111.4958% delta=1113.1816pp
- liq>=100k & tx>=250: N=139 ROI=1868.1707% delta=869.8565pp
- turnover<=1: N=145 ROI=1785.7549% delta=787.4407pp
- liq>=100k & vol>=50k: N=148 ROI=1753.8694% delta=755.5552pp
- vol>=100k: N=150 ROI=1715.7371% delta=717.4229pp
- liq>=100k: N=181 ROI=1434.0423% delta=435.7281pp
- vol>=50k: N=197 ROI=1297.7407% delta=299.4265pp

## Missed-star scan
- Candidates: 889
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 57, 'LIQ_LT_50K': 795, 'VOL_LT_15K': 556, 'TX_LT_50': 443}

Research only; validate prospectively before changing production gates.
