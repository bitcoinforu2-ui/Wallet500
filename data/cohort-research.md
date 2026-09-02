# Wallet500 Cohort Research

Generated: 2026-09-02T09:57:38.985417+00:00
Source snapshot: 2026-09-02T09:57:36.112178+00:00

## Baseline
- N=354 ROI=3.519135245365817e+37% P/L=$1.2457738768594992e+38

## Best post-hoc counterfactuals (min 5 retained)
- pre-runup<=10%: N=158 ROI=7.884644790249995e+37% delta=4.365509544884177e+37pp
- pre-runup<=25%: N=181 ROI=6.882728601433698e+37% delta=3.363593356067881e+37pp
- pre-runup<=50%: N=182 ROI=6.84491141131593e+37% delta=3.3257761659501134e+37pp
- pre-runup<=100%: N=182 ROI=6.84491141131593e+37% delta=3.3257761659501134e+37pp
- turnover<=1: N=192 ROI=6.488405608643225e+37% delta=2.969270363277408e+37pp
- turnover>=0.5: N=200 ROI=6.228869384297496e+37% delta=2.709734138931679e+37pp
- turnover<=2: N=280 ROI=4.449192417355354e+37% delta=9.30057171989537e+36pp
- liq>=75k: N=286 ROI=4.355852716291955e+37% delta=8.367174709261377e+36pp
- turnover>=0.25: N=296 ROI=4.2086955299307403e+37% delta=6.895602845649235e+36pp
- tx>=100: N=324 ROI=3.8449811014182073e+37% delta=3.258458560523905e+36pp

## Missed-star scan
- Candidates: 1163
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 77, 'LIQ_LT_50K': 1039, 'VOL_LT_15K': 720, 'TX_LT_50': 575}

Research only; validate prospectively before changing production gates.
