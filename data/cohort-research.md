# Wallet500 Cohort Research

Generated: 2026-09-14T01:53:36.906265+00:00
Source snapshot: 2026-09-14T01:46:53.604458+00:00

## Baseline
- N=359 ROI=-0.8097% P/L=$-2.906976

## Best post-hoc counterfactuals (min 5 retained)
- liq>=250k: N=128 ROI=-0.3864% delta=0.4233pp
- liq>=500k: N=174 ROI=-0.4421% delta=0.3676pp
- turnover<=1: N=193 ROI=-0.4997% delta=0.31pp
- vol>=50k: N=359 ROI=-0.8097% delta=0.0pp
- turnover<=2: N=285 ROI=-0.8138% delta=-0.0041pp
- liq>=100k: N=232 ROI=-0.8466% delta=-0.0369pp
- liq>=100k & vol>=50k: N=232 ROI=-0.8466% delta=-0.0369pp
- tx>=100: N=328 ROI=-0.9146% delta=-0.1049pp
- vol>=25k: N=330 ROI=-0.935% delta=-0.1253pp
- liq>=75k: N=286 ROI=-1.0364% delta=-0.2267pp

## Missed-star scan
- Candidates: 1165
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 71, 'LIQ_LT_15K': 1047, 'VOL_LT_15K': 723, 'TX_LT_50': 588}

Research only; validate prospectively before changing production gates.
