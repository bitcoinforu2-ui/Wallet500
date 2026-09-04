# Wallet500 Cohort Research

Generated: 2026-09-04T22:29:40.843774+00:00
Source snapshot: 2026-09-04T22:22:33.545844+00:00

## Baseline
- N=355 ROI=-0.7277% P/L=$-2.583302

## Best post-hoc counterfactuals (min 5 retained)
- turnover<=1: N=192 ROI=-0.3337% delta=0.394pp
- liq>=250k: N=128 ROI=-0.3864% delta=0.3413pp
- liq>=100k: N=232 ROI=-0.7071% delta=0.0206pp
- turnover<=2: N=281 ROI=-0.7102% delta=0.0175pp
- tx>=100: N=325 ROI=-0.8235% delta=-0.0958pp
- vol>=25k: N=328 ROI=-0.842% delta=-0.1143pp
- liq>=75k: N=286 ROI=-0.9232% delta=-0.1955pp
- tx>=500: N=183 ROI=-0.9396% delta=-0.2119pp
- tx>=250: N=282 ROI=-0.9643% delta=-0.2366pp
- liq>=100k & tx>=250: N=182 ROI=-0.9761% delta=-0.2484pp

## Missed-star scan
- Candidates: 1165
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 76, 'LIQ_LT_50K': 1042, 'VOL_LT_15K': 718, 'TX_LT_50': 580}

Research only; validate prospectively before changing production gates.
