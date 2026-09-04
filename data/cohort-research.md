# Wallet500 Cohort Research

Generated: 2026-09-04T07:53:21.839412+00:00
Source snapshot: 2026-09-04T07:53:19.575489+00:00

## Baseline
- N=355 ROI=3.509222188336618e+37% P/L=$1.2457738768594992e+38

## Best post-hoc counterfactuals (min 5 retained)
- pre-runup<=10%: N=159 ROI=7.835055829305026e+37% delta=4.325833640968409e+37pp
- pre-runup<=25%: N=182 ROI=6.84491141131593e+37% delta=3.3356892229793124e+37pp
- pre-runup<=50%: N=183 ROI=6.807507523822399e+37% delta=3.2982853354857817e+37pp
- pre-runup<=100%: N=183 ROI=6.807507523822399e+37% delta=3.2982853354857817e+37pp
- turnover<=1: N=192 ROI=6.488405608643225e+37% delta=2.979183420306607e+37pp
- turnover>=0.5: N=201 ROI=6.197879984375618e+37% delta=2.6886577960390004e+37pp
- turnover<=2: N=281 ROI=4.433358992382559e+37% delta=9.241368040459414e+36pp
- liq>=75k: N=286 ROI=4.355852716291955e+37% delta=8.466305279553367e+36pp
- turnover>=0.25: N=297 ROI=4.194524837910772e+37% delta=6.853026495741542e+36pp
- tx>=100: N=325 ROI=3.8331503903369206e+37% delta=3.2392820200030277e+36pp

## Missed-star scan
- Candidates: 1165
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 76, 'LIQ_LT_50K': 1042, 'VOL_LT_15K': 718, 'TX_LT_50': 580}

Research only; validate prospectively before changing production gates.
