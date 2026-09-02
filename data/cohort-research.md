# Wallet500 Cohort Research

Generated: 2026-09-02T07:59:32.887908+00:00
Source snapshot: 2026-09-02T07:59:29.760877+00:00

## Baseline
- N=344 ROI=3.6214356885450555e+37% P/L=$1.2457738768594992e+38

## Best post-hoc counterfactuals (min 5 retained)
- pre-runup<=10%: N=155 ROI=8.037250818448381e+37% delta=4.415815129903325e+37pp
- pre-runup<=25%: N=175 ROI=7.118707867768566e+37% delta=3.497272179223511e+37pp
- pre-runup<=50%: N=176 ROI=7.078260663974427e+37% delta=3.456824975429372e+37pp
- pre-runup<=100%: N=176 ROI=7.078260663974427e+37% delta=3.456824975429372e+37pp
- turnover<=1: N=187 ROI=6.66189238962299e+37% delta=3.040456701077935e+37pp
- turnover>=0.5: N=192 ROI=6.488405608643225e+37% delta=2.8669699200981694e+37pp
- turnover<=2: N=271 ROI=4.596951575127304e+37% delta=9.755158865822484e+36pp
- liq>=75k: N=279 ROI=4.465139343582435e+37% delta=8.437036550373792e+36pp
- turnover>=0.25: N=286 ROI=4.355852716291955e+37% delta=7.344170277468991e+36pp
- tx>=100: N=314 ROI=3.967432728851908e+37% delta=3.459970403068527e+36pp

## Missed-star scan
- Candidates: 1137
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 75, 'LIQ_LT_50K': 1016, 'VOL_LT_15K': 703, 'TX_LT_50': 559}

Research only; validate prospectively before changing production gates.
