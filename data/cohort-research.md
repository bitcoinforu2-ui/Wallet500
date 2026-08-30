# Wallet500 Cohort Research

Generated: 2026-08-30T19:18:55.189281+00:00
Source snapshot: 2026-08-30T19:18:54.005190+00:00

## Baseline
- N=45 ROI=-6.9567% P/L=$-3.130508

## Best post-hoc counterfactuals (min 5 retained)
- liq>=500k: N=22 ROI=2.6522% delta=9.6089pp
- liq>=250k & vol>=100k: N=24 ROI=2.2864% delta=9.2431pp
- liq>=250k: N=29 ROI=2.0202% delta=8.9769pp
- pre-runup<=10%: N=25 ROI=-1.2712% delta=5.6855pp
- turnover<=1: N=32 ROI=-2.0408% delta=4.9159pp
- liq>=75k: N=39 ROI=-2.1831% delta=4.7736pp
- liq>=100k & vol>=50k: N=33 ROI=-2.4082% delta=4.5485pp
- liq>=100k: N=37 ROI=-2.7112% delta=4.2455pp
- turnover<=2: N=37 ROI=-2.7889% delta=4.1678pp
- liq>=100k & tx>=250: N=23 ROI=-3.2359% delta=3.7208pp

## Missed-star scan
- Candidates: 382
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 29, 'LIQ_LT_50K': 332, 'VOL_LT_15K': 248, 'TX_LT_50': 211}

Research only; validate prospectively before changing production gates.
