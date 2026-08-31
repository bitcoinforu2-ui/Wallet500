# Wallet500 Cohort Research

Generated: 2026-08-31T10:38:26.715207+00:00
Source snapshot: 2026-08-31T10:38:25.043580+00:00

## Baseline
- N=121 ROI=-21.8136% P/L=$-26.39445

## Best post-hoc counterfactuals (min 5 retained)
- liq>=250k: N=54 ROI=-3.9594% delta=17.8542pp
- liq>=250k & vol>=100k: N=43 ROI=-4.3288% delta=17.4848pp
- turnover<=1: N=73 ROI=-5.8468% delta=15.9668pp
- liq>=500k: N=34 ROI=-6.2474% delta=15.5662pp
- liq>=100k: N=86 ROI=-9.8651% delta=11.9485pp
- liq>=100k & vol>=50k: N=72 ROI=-11.3396% delta=10.474pp
- liq>=100k & tx>=250: N=63 ROI=-12.5287% delta=9.2849pp
- tx>=500: N=53 ROI=-15.9535% delta=5.8601pp
- liq>=75k: N=101 ROI=-18.386% delta=3.4276pp
- turnover<=2: N=99 ROI=-22.2977% delta=-0.4841pp

## Missed-star scan
- Candidates: 555
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 43, 'LIQ_LT_50K': 487, 'VOL_LT_15K': 352, 'TX_LT_50': 290}

Research only; validate prospectively before changing production gates.
