# Wallet500 Cohort Research

Generated: 2026-09-02T06:23:46.456269+00:00
Source snapshot: 2026-09-02T06:23:44.284723+00:00

## Baseline
- N=333 ROI=3.7410626932717696e+37% P/L=$1.2457738768594992e+38

## Best post-hoc counterfactuals (min 5 retained)
- pre-runup<=10%: N=152 ROI=8.195880768812495e+37% delta=4.454818075540726e+37pp
- pre-runup<=25%: N=171 ROI=7.285227350055552e+37% delta=3.544164656783782e+37pp
- pre-runup<=50%: N=172 ROI=7.242871377090111e+37% delta=3.5018086838183413e+37pp
- pre-runup<=100%: N=172 ROI=7.242871377090111e+37% delta=3.5018086838183413e+37pp
- turnover<=1: N=180 ROI=6.920965982552774e+37% delta=3.179903289281004e+37pp
- turnover>=0.5: N=187 ROI=6.66189238962299e+37% delta=2.9208296963512207e+37pp
- turnover<=2: N=260 ROI=4.791437987921151e+37% delta=1.0503752946493813e+37pp
- liq>=75k: N=271 ROI=4.596951575127304e+37% delta=8.558888818555342e+36pp
- turnover>=0.25: N=277 ROI=4.497378616821297e+37% delta=7.563159235495275e+36pp
- tx>=100: N=304 ROI=4.0979403844062476e+37% delta=3.56877691134478e+36pp

## Missed-star scan
- Candidates: 1107
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 73, 'LIQ_LT_50K': 988, 'VOL_LT_15K': 685, 'TX_LT_50': 551}

Research only; validate prospectively before changing production gates.
