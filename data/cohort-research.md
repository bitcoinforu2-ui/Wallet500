# Wallet500 Cohort Research

Generated: 2026-09-02T06:44:51.431648+00:00
Source snapshot: 2026-09-02T06:44:48.420282+00:00

## Baseline
- N=336 ROI=3.7076603477961283e+37% P/L=$1.2457738768594992e+38

## Best post-hoc counterfactuals (min 5 retained)
- pre-runup<=10%: N=152 ROI=8.195880768812495e+37% delta=4.488220421016367e+37pp
- pre-runup<=25%: N=171 ROI=7.285227350055552e+37% delta=3.5775670022594234e+37pp
- pre-runup<=50%: N=172 ROI=7.242871377090111e+37% delta=3.5352110292939826e+37pp
- pre-runup<=100%: N=172 ROI=7.242871377090111e+37% delta=3.5352110292939826e+37pp
- turnover<=1: N=181 ROI=6.882728601433698e+37% delta=3.1750682536375694e+37pp
- turnover>=0.5: N=189 ROI=6.591396173859785e+37% delta=2.8837358260636563e+37pp
- turnover<=2: N=263 ROI=4.736782801747146e+37% delta=1.0291224539510176e+37pp
- liq>=75k: N=273 ROI=4.56327427421062e+37% delta=8.556139264144915e+36pp
- turnover>=0.25: N=280 ROI=4.449192417355354e+37% delta=7.415320695592255e+36pp
- tx>=100: N=307 ROI=4.05789536436319e+37% delta=3.502350165670615e+36pp

## Missed-star scan
- Candidates: 1113
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 73, 'LIQ_LT_50K': 995, 'VOL_LT_15K': 689, 'TX_LT_50': 550}

Research only; validate prospectively before changing production gates.
