# Wallet500 Cohort Research

Generated: 2026-08-31T21:41:30.999316+00:00
Source snapshot: 2026-08-31T21:41:29.026107+00:00

## Baseline
- N=162 ROI=-18.3387% P/L=$-29.708657

## Best post-hoc counterfactuals (min 5 retained)
- liq>=250k & vol>=100k: N=54 ROI=5.4538% delta=23.7925pp
- liq>=250k: N=71 ROI=5.0879% delta=23.4266pp
- liq>=500k: N=41 ROI=-3.6071% delta=14.7316pp
- liq>=100k: N=117 ROI=-6.8216% delta=11.5171pp
- turnover<=1: N=94 ROI=-6.8345% delta=11.5042pp
- liq>=100k & tx>=250: N=87 ROI=-7.7407% delta=10.598pp
- liq>=100k & vol>=50k: N=97 ROI=-8.5253% delta=9.8134pp
- tx>=500: N=74 ROI=-8.7077% delta=9.631pp
- liq>=75k: N=136 ROI=-14.6288% delta=3.7099pp
- vol>=100k: N=95 ROI=-19.6393% delta=-1.3006pp

## Missed-star scan
- Candidates: 659
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 45, 'LIQ_LT_50K': 586, 'VOL_LT_15K': 414, 'TX_LT_50': 338}

Research only; validate prospectively before changing production gates.
