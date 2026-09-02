# Wallet500 Cohort Research

Generated: 2026-09-02T09:40:38.647209+00:00
Source snapshot: 2026-09-02T09:40:35.558378+00:00

## Baseline
- N=352 ROI=3.5391303319872137e+37% P/L=$1.2457738768594992e+38

## Best post-hoc counterfactuals (min 5 retained)
- pre-runup<=10%: N=157 ROI=7.934865457703816e+37% delta=4.395735125716603e+37pp
- pre-runup<=25%: N=179 ROI=6.959630596980443e+37% delta=3.4205002649932294e+37pp
- pre-runup<=50%: N=180 ROI=6.920965982552774e+37% delta=3.38183565056556e+37pp
- pre-runup<=100%: N=180 ROI=6.920965982552774e+37% delta=3.38183565056556e+37pp
- turnover<=1: N=191 ROI=6.522376318636121e+37% delta=2.9832459866489075e+37pp
- turnover>=0.5: N=198 ROI=6.291787256866158e+37% delta=2.752656924878944e+37pp
- turnover<=2: N=278 ROI=4.481200995897479e+37% delta=9.42070663910265e+36pp
- liq>=75k: N=284 ROI=4.386527735420772e+37% delta=8.47397403433558e+36pp
- turnover>=0.25: N=294 ROI=4.2373261117670047e+37% delta=6.98195779779791e+36pp
- tx>=100: N=322 ROI=3.8688629716133515e+37% delta=3.297326396261378e+36pp

## Missed-star scan
- Candidates: 1158
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 77, 'LIQ_LT_50K': 1035, 'VOL_LT_15K': 715, 'TX_LT_50': 568}

Research only; validate prospectively before changing production gates.
