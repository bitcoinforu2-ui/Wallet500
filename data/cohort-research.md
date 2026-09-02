# Wallet500 Cohort Research

Generated: 2026-09-02T08:31:13.159097+00:00
Source snapshot: 2026-09-02T08:31:09.984180+00:00

## Baseline
- N=347 ROI=3.590126446280977e+37% P/L=$1.2457738768594992e+38

## Best post-hoc counterfactuals (min 5 retained)
- pre-runup<=10%: N=156 ROI=7.985729979868584e+37% delta=4.395603533587607e+37pp
- pre-runup<=25%: N=176 ROI=7.078260663974427e+37% delta=3.48813421769345e+37pp
- pre-runup<=50%: N=177 ROI=7.038270490731634e+37% delta=3.4481440444506565e+37pp
- pre-runup<=100%: N=177 ROI=7.038270490731634e+37% delta=3.4481440444506565e+37pp
- turnover<=1: N=188 ROI=6.626456791805846e+37% delta=3.036330345524869e+37pp
- turnover>=0.5: N=194 ROI=6.421514829172677e+37% delta=2.8313883828916995e+37pp
- turnover<=2: N=273 ROI=4.56327427421062e+37% delta=9.731478279296427e+36pp
- liq>=75k: N=281 ROI=4.433358992382559e+37% delta=8.432325461015821e+36pp
- turnover>=0.25: N=289 ROI=4.310636252108994e+37% delta=7.205098058280174e+36pp
- tx>=100: N=317 ROI=3.9298860468753915e+37% delta=3.3975960059441444e+36pp

## Missed-star scan
- Candidates: 1145
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 76, 'LIQ_LT_50K': 1023, 'VOL_LT_15K': 709, 'TX_LT_50': 563}

Research only; validate prospectively before changing production gates.
