# Wallet500 Cohort Research

Generated: 2026-09-02T02:05:37.727097+00:00
Source snapshot: 2026-09-02T02:05:34.927125+00:00

## Baseline
- N=315 ROI=3.9548377043158708e+37% P/L=$1.2457738768594992e+38

## Best post-hoc counterfactuals (min 5 retained)
- pre-runup<=10%: N=143 ROI=8.71170543258391e+37% delta=4.756867728268038e+37pp
- pre-runup<=25%: N=160 ROI=7.78608673037187e+37% delta=3.8312490260559993e+37pp
- pre-runup<=50%: N=161 ROI=7.737725943226703e+37% delta=3.782888238910832e+37pp
- pre-runup<=100%: N=161 ROI=7.737725943226703e+37% delta=3.782888238910832e+37pp
- turnover>=0.5: N=173 ROI=7.201005068552018e+37% delta=3.2461673642361476e+37pp
- turnover<=1: N=176 ROI=7.078260663974427e+37% delta=3.1234229596585566e+37pp
- turnover<=2: N=247 ROI=5.043618934653842e+37% delta=1.0887812303379715e+37pp
- liq>=75k: N=256 ROI=4.866304206482419e+37% delta=9.114665021665479e+36pp
- turnover>=0.25: N=260 ROI=4.791437987921151e+37% delta=8.366002836052802e+36pp
- tx>=100: N=287 ROI=4.340675529127175e+37% delta=3.8583782481130396e+36pp

## Missed-star scan
- Candidates: 1054
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 66, 'LIQ_LT_50K': 944, 'VOL_LT_15K': 653, 'TX_LT_50': 520}

Research only; validate prospectively before changing production gates.
