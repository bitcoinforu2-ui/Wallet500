# Wallet500 Cohort Research

Generated: 2026-09-02T02:46:31.148387+00:00
Source snapshot: 2026-09-02T02:46:28.275364+00:00

## Baseline
- N=319 ROI=3.9052472628824426e+37% P/L=$1.2457738768594992e+38

## Best post-hoc counterfactuals (min 5 retained)
- pre-runup<=10%: N=145 ROI=8.591543978341374e+37% delta=4.686296715458931e+37pp
- pre-runup<=25%: N=162 ROI=7.689962202836415e+37% delta=3.784714939953972e+37pp
- pre-runup<=50%: N=163 ROI=7.6427845206104245e+37% delta=3.737537257727982e+37pp
- pre-runup<=100%: N=163 ROI=7.6427845206104245e+37% delta=3.737537257727982e+37pp
- turnover>=0.5: N=176 ROI=7.078260663974427e+37% delta=3.1730134010919847e+37pp
- turnover<=1: N=177 ROI=7.038270490731634e+37% delta=3.133023227849191e+37pp
- turnover<=2: N=250 ROI=4.983095507437998e+37% delta=1.077848244555555e+37pp
- liq>=75k: N=259 ROI=4.809937748492274e+37% delta=9.046904856098318e+36pp
- turnover>=0.25: N=264 ROI=4.718840442649618e+37% delta=8.13593179767175e+36pp
- tx>=100: N=291 ROI=4.281009886115117e+37% delta=3.7576262323267413e+36pp

## Missed-star scan
- Candidates: 1072
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 70, 'LIQ_LT_50K': 959, 'VOL_LT_15K': 663, 'TX_LT_50': 528}

Research only; validate prospectively before changing production gates.
