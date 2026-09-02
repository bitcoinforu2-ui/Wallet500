# Wallet500 Cohort Research

Generated: 2026-09-02T04:18:40.770323+00:00
Source snapshot: 2026-09-02T04:18:37.871598+00:00

## Baseline
- N=323 ROI=3.8568850676764686e+37% P/L=$1.2457738768594992e+38

## Best post-hoc counterfactuals (min 5 retained)
- pre-runup<=10%: N=145 ROI=8.591543978341374e+37% delta=4.734658910664905e+37pp
- pre-runup<=25%: N=164 ROI=7.596182175972556e+37% delta=3.7392971082960874e+37pp
- pre-runup<=50%: N=165 ROI=7.5501447082393885e+37% delta=3.69325964056292e+37pp
- pre-runup<=100%: N=165 ROI=7.5501447082393885e+37% delta=3.69325964056292e+37pp
- turnover<=1: N=177 ROI=7.038270490731634e+37% delta=3.181385423055165e+37pp
- turnover>=0.5: N=180 ROI=6.920965982552774e+37% delta=3.064080914876305e+37pp
- turnover<=2: N=252 ROI=4.943547130394838e+37% delta=1.0866620627183692e+37pp
- liq>=75k: N=263 ROI=4.736782801747146e+37% delta=8.798977340706773e+36pp
- turnover>=0.25: N=268 ROI=4.648409988281713e+37% delta=7.915249206052446e+36pp
- tx>=100: N=295 ROI=4.2229622944389804e+37% delta=3.660772267625118e+36pp

## Missed-star scan
- Candidates: 1084
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 72, 'LIQ_LT_50K': 968, 'VOL_LT_15K': 670, 'TX_LT_50': 535}

Research only; validate prospectively before changing production gates.
