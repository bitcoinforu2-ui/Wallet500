# Wallet500 Cohort Research

Generated: 2026-09-20T02:53:38.023817+00:00
Source snapshot: 2026-09-20T02:47:32.240183+00:00

## Baseline
- N=359 ROI=-1.0092% P/L=$-3.622894

## Best post-hoc counterfactuals (min 5 retained)
- turnover<=1: N=193 ROI=-0.3525% delta=0.6567pp
- liq>=250k: N=128 ROI=-0.3864% delta=0.6228pp
- liq>=500k: N=174 ROI=-0.4421% delta=0.5671pp
- liq>=100k: N=232 ROI=-0.7242% delta=0.285pp
- liq>=100k & vol>=50k: N=232 ROI=-0.7242% delta=0.285pp
- liq>=75k: N=286 ROI=-0.9371% delta=0.0721pp
- tx>=500: N=184 ROI=-0.956% delta=0.0532pp
- tx>=250: N=283 ROI=-0.9749% delta=0.0343pp
- liq>=100k & tx>=250: N=182 ROI=-0.9979% delta=0.0113pp
- vol>=50k: N=359 ROI=-1.0092% delta=0.0pp

## Missed-star scan
- Candidates: 1165
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 71, 'LIQ_LT_15K': 1047, 'VOL_LT_15K': 723, 'TX_LT_50': 588}

Research only; validate prospectively before changing production gates.
