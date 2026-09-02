# Wallet500 Cohort Research

Generated: 2026-09-02T02:21:34.623733+00:00
Source snapshot: 2026-09-02T02:21:31.692663+00:00

## Baseline
- N=317 ROI=3.9298860468753915e+37% P/L=$1.2457738768594992e+38

## Best post-hoc counterfactuals (min 5 retained)
- pre-runup<=10%: N=144 ROI=8.651207478190967e+37% delta=4.721321431315575e+37pp
- pre-runup<=25%: N=161 ROI=7.737725943226703e+37% delta=3.8078398963513114e+37pp
- pre-runup<=50%: N=162 ROI=7.689962202836415e+37% delta=3.760076155961023e+37pp
- pre-runup<=100%: N=162 ROI=7.689962202836415e+37% delta=3.760076155961023e+37pp
- turnover>=0.5: N=174 ROI=7.159619981951144e+37% delta=3.229733935075753e+37pp
- turnover<=1: N=177 ROI=7.038270490731634e+37% delta=3.108384443856242e+37pp
- turnover<=2: N=249 ROI=5.003107939194776e+37% delta=1.0732218923193845e+37pp
- liq>=75k: N=258 ROI=4.828580918060074e+37% delta=8.986948711846827e+36pp
- turnover>=0.25: N=262 ROI=4.754862125417936e+37% delta=8.249760785425442e+36pp
- tx>=100: N=289 ROI=4.310636252108994e+37% delta=3.807502052336029e+36pp

## Missed-star scan
- Candidates: 1064
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 68, 'LIQ_LT_50K': 951, 'VOL_LT_15K': 659, 'TX_LT_50': 526}

Research only; validate prospectively before changing production gates.
