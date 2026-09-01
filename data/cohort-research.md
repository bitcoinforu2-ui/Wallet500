# Wallet500 Cohort Research

Generated: 2026-09-01T06:06:54.906135+00:00
Source snapshot: 2026-09-01T06:06:52.771111+00:00

## Baseline
- N=205 ROI=-14.0299% P/L=$-28.761343

## Best post-hoc counterfactuals (min 5 retained)
- liq>=250k & vol>=100k: N=71 ROI=21.8236% delta=35.8535pp
- liq>=250k: N=92 ROI=17.4766% delta=31.5065pp
- tx>=500: N=94 ROI=5.1084% delta=19.1383pp
- liq>=100k & tx>=250: N=110 ROI=3.2045% delta=17.2344pp
- liq>=100k & vol>=50k: N=120 ROI=2.0953% delta=16.1252pp
- liq>=100k: N=146 ROI=1.9639% delta=15.9938pp
- liq>=500k: N=54 ROI=-4.568% delta=9.4619pp
- turnover<=1: N=119 ROI=-6.1906% delta=7.8393pp
- liq>=75k: N=173 ROI=-9.5151% delta=4.5148pp
- vol>=100k: N=122 ROI=-11.4454% delta=2.5845pp

## Missed-star scan
- Candidates: 770
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 49, 'LIQ_LT_50K': 687, 'VOL_LT_15K': 478, 'TX_LT_50': 379}

Research only; validate prospectively before changing production gates.
