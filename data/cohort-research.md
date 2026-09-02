# Wallet500 Cohort Research

Generated: 2026-09-02T07:30:04.427228+00:00
Source snapshot: 2026-09-02T07:30:01.240816+00:00

## Baseline
- N=342 ROI=3.642613675027776e+37% P/L=$1.2457738768594992e+38

## Best post-hoc counterfactuals (min 5 retained)
- pre-runup<=10%: N=154 ROI=8.089440758827916e+37% delta=4.44682708380014e+37pp
- pre-runup<=25%: N=174 ROI=7.159619981951144e+37% delta=3.5170063069233685e+37pp
- pre-runup<=50%: N=175 ROI=7.118707867768566e+37% delta=3.4760941927407904e+37pp
- pre-runup<=100%: N=175 ROI=7.118707867768566e+37% delta=3.4760941927407904e+37pp
- turnover<=1: N=185 ROI=6.733912847889185e+37% delta=3.091299172861409e+37pp
- turnover>=0.5: N=191 ROI=6.522376318636121e+37% delta=2.8797626436083452e+37pp
- turnover<=2: N=269 ROI=4.631129653752786e+37% delta=9.885159787250099e+36pp
- liq>=75k: N=278 ROI=4.481200995897479e+37% delta=8.385873208697028e+36pp
- turnover>=0.25: N=284 ROI=4.386527735420772e+37% delta=7.439140603929958e+36pp
- tx>=100: N=312 ROI=3.992864989934292e+37% delta=3.502513149065161e+36pp

## Missed-star scan
- Candidates: 1123
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 75, 'LIQ_LT_50K': 1002, 'VOL_LT_15K': 697, 'TX_LT_50': 555}

Research only; validate prospectively before changing production gates.
