# Wallet500 Cohort Research

Generated: 2026-09-02T01:04:19.143181+00:00
Source snapshot: 2026-09-02T01:04:16.370601+00:00

## Baseline
- N=312 ROI=3.992864989934292e+37% P/L=$1.2457738768594992e+38

## Best post-hoc counterfactuals (min 5 retained)
- pre-runup<=10%: N=141 ROI=8.835275722407796e+37% delta=4.842410732473505e+37pp
- pre-runup<=25%: N=158 ROI=7.884644790249995e+37% delta=3.8917798003157026e+37pp
- pre-runup<=50%: N=159 ROI=7.835055829305026e+37% delta=3.842190839370734e+37pp
- pre-runup<=100%: N=159 ROI=7.835055829305026e+37% delta=3.842190839370734e+37pp
- turnover>=0.5: N=172 ROI=7.242871377090111e+37% delta=3.250006387155819e+37pp
- turnover<=1: N=174 ROI=7.159619981951144e+37% delta=3.1667549920168524e+37pp
- turnover<=2: N=244 ROI=5.1056306428668e+37% delta=1.1127656529325079e+37pp
- liq>=75k: N=253 ROI=4.9240074184169925e+37% delta=9.311424284827005e+36pp
- turnover>=0.25: N=258 ROI=4.828580918060074e+37% delta=8.357159281257823e+36pp
- tx>=100: N=284 ROI=4.386527735420772e+37% delta=3.936627454864797e+36pp

## Missed-star scan
- Candidates: 1046
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 66, 'LIQ_LT_50K': 938, 'VOL_LT_15K': 646, 'TX_LT_50': 516}

Research only; validate prospectively before changing production gates.
