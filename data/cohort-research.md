# Wallet500 Cohort Research

Generated: 2026-09-02T07:01:58.139225+00:00
Source snapshot: 2026-09-02T07:01:55.089099+00:00

## Baseline
- N=338 ROI=3.685721529170116e+37% P/L=$1.2457738768594992e+38

## Best post-hoc counterfactuals (min 5 retained)
- pre-runup<=10%: N=152 ROI=8.195880768812495e+37% delta=4.51015923964238e+37pp
- pre-runup<=25%: N=172 ROI=7.242871377090111e+37% delta=3.557149847919995e+37pp
- pre-runup<=50%: N=173 ROI=7.201005068552018e+37% delta=3.5152835393819025e+37pp
- pre-runup<=100%: N=173 ROI=7.201005068552018e+37% delta=3.5152835393819025e+37pp
- turnover<=1: N=182 ROI=6.84491141131593e+37% delta=3.1591898821458143e+37pp
- turnover>=0.5: N=190 ROI=6.556704615049995e+37% delta=2.8709830858798795e+37pp
- turnover<=2: N=265 ROI=4.701033497583016e+37% delta=1.0153119684128998e+37pp
- liq>=75k: N=275 ROI=4.5300868249436335e+37% delta=8.443652957735176e+36pp
- turnover>=0.25: N=281 ROI=4.433358992382559e+37% delta=7.476374632124433e+36pp
- tx>=100: N=309 ROI=4.031630669448218e+37% delta=3.4590914027810206e+36pp

## Missed-star scan
- Candidates: 1120
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 75, 'LIQ_LT_50K': 999, 'VOL_LT_15K': 694, 'TX_LT_50': 554}

Research only; validate prospectively before changing production gates.
