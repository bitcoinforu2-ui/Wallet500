# Wallet500 Cohort Research

Generated: 2026-08-31T00:06:31.721967+00:00
Source snapshot: 2026-08-31T00:06:30.409841+00:00

## Baseline
- N=68 ROI=-17.3676% P/L=$-11.809967

## Best post-hoc counterfactuals (min 5 retained)
- liq>=250k: N=39 ROI=-4.0801% delta=13.2875pp
- liq>=250k & vol>=100k: N=31 ROI=-4.3071% delta=13.0605pp
- liq>=500k: N=27 ROI=-5.5762% delta=11.7914pp
- liq>=100k: N=52 ROI=-7.5652% delta=9.8024pp
- liq>=100k & vol>=50k: N=46 ROI=-7.9756% delta=9.392pp
- turnover<=1: N=47 ROI=-8.3189% delta=9.0487pp
- liq>=100k & tx>=250: N=34 ROI=-8.6436% delta=8.724pp
- vol>=100k: N=42 ROI=-12.2119% delta=5.1557pp
- liq>=75k: N=58 ROI=-13.4175% delta=3.9501pp
- tx>=500: N=31 ROI=-15.3412% delta=2.0264pp

## Missed-star scan
- Candidates: 432
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 31, 'LIQ_LT_50K': 381, 'VOL_LT_15K': 282, 'TX_LT_50': 242}

Research only; validate prospectively before changing production gates.
