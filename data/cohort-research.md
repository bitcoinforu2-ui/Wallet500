# Wallet500 Cohort Research

Generated: 2026-08-31T16:39:34.437451+00:00
Source snapshot: 2026-08-31T16:39:32.593555+00:00

## Baseline
- N=140 ROI=-19.3015% P/L=$-27.022166

## Best post-hoc counterfactuals (min 5 retained)
- liq>=250k & vol>=100k: N=48 ROI=2.3074% delta=21.6089pp
- liq>=250k: N=61 ROI=1.442% delta=20.7435pp
- liq>=500k: N=39 ROI=-5.305% delta=13.9965pp
- turnover<=1: N=81 ROI=-5.6057% delta=13.6958pp
- liq>=100k: N=101 ROI=-8.3962% delta=10.9053pp
- liq>=100k & vol>=50k: N=85 ROI=-9.4477% delta=9.8538pp
- liq>=100k & tx>=250: N=74 ROI=-10.0911% delta=9.2104pp
- tx>=500: N=63 ROI=-10.4881% delta=8.8134pp
- liq>=75k: N=117 ROI=-15.9229% delta=3.3786pp
- vol>=25k: N=132 ROI=-20.6272% delta=-1.3257pp

## Missed-star scan
- Candidates: 616
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 44, 'LIQ_LT_50K': 547, 'VOL_LT_15K': 395, 'TX_LT_50': 325}

Research only; validate prospectively before changing production gates.
