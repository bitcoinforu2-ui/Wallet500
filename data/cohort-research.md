# Wallet500 Cohort Research

Generated: 2026-09-02T06:08:53.921081+00:00
Source snapshot: 2026-09-02T06:08:51.052154+00:00

## Baseline
- N=329 ROI=3.7865467381747693e+37% P/L=$1.2457738768594992e+38

## Best post-hoc counterfactuals (min 5 retained)
- pre-runup<=10%: N=151 ROI=8.250158124897346e+37% delta=4.463611386722576e+37pp
- pre-runup<=25%: N=170 ROI=7.32808162858529e+37% delta=3.5415348904105206e+37pp
- pre-runup<=50%: N=171 ROI=7.285227350055552e+37% delta=3.4986806118807824e+37pp
- pre-runup<=100%: N=171 ROI=7.285227350055552e+37% delta=3.4986806118807824e+37pp
- turnover<=1: N=178 ROI=6.998729645278087e+37% delta=3.212182907103317e+37pp
- turnover>=0.5: N=185 ROI=6.733912847889185e+37% delta=2.9473661097144154e+37pp
- turnover<=2: N=257 ROI=4.84736917065953e+37% delta=1.0608224324847606e+37pp
- liq>=75k: N=267 ROI=4.665819763518724e+37% delta=8.792730253439544e+36pp
- turnover>=0.25: N=273 ROI=4.56327427421062e+37% delta=7.767275360358505e+36pp
- tx>=100: N=300 ROI=4.152579589531664e+37% delta=3.660328513568945e+36pp

## Missed-star scan
- Candidates: 1101
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 72, 'LIQ_LT_50K': 984, 'VOL_LT_15K': 682, 'TX_LT_50': 546}

Research only; validate prospectively before changing production gates.
