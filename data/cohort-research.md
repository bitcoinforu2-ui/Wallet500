# Wallet500 Cohort Research

Generated: 2026-09-02T09:00:08.787234+00:00
Source snapshot: 2026-09-02T09:00:05.777895+00:00

## Baseline
- N=349 ROI=3.5695526557578776e+37% P/L=$1.2457738768594992e+38

## Best post-hoc counterfactuals (min 5 retained)
- pre-runup<=10%: N=156 ROI=7.985729979868584e+37% delta=4.416177324110706e+37pp
- pre-runup<=25%: N=178 ROI=6.998729645278087e+37% delta=3.429176989520209e+37pp
- pre-runup<=50%: N=179 ROI=6.959630596980443e+37% delta=3.3900779412225655e+37pp
- pre-runup<=100%: N=179 ROI=6.959630596980443e+37% delta=3.3900779412225655e+37pp
- turnover<=1: N=189 ROI=6.591396173859785e+37% delta=3.021843518101907e+37pp
- turnover>=0.5: N=196 ROI=6.355989167650507e+37% delta=2.786436511892629e+37pp
- turnover<=2: N=275 ROI=4.5300868249436335e+37% delta=9.605341691857559e+36pp
- liq>=75k: N=282 ROI=4.417637861203898e+37% delta=8.480852054460206e+36pp
- turnover>=0.25: N=291 ROI=4.281009886115117e+37% delta=7.114572303572392e+36pp
- tx>=100: N=319 ROI=3.9052472628824426e+37% delta=3.3569460712456507e+36pp

## Missed-star scan
- Candidates: 1152
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 76, 'LIQ_LT_50K': 1030, 'VOL_LT_15K': 712, 'TX_LT_50': 566}

Research only; validate prospectively before changing production gates.
