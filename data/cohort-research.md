# Wallet500 Cohort Research

Generated: 2026-09-25T17:42:49.948102+00:00
Source snapshot: 2026-09-25T17:35:58.585642+00:00

## Baseline
- N=359 ROI=-0.7779% P/L=$-2.79269

## Best post-hoc counterfactuals (min 5 retained)
- liq>=250k: N=128 ROI=-0.3864% delta=0.3915pp
- turnover<=1: N=193 ROI=-0.4405% delta=0.3374pp
- liq>=500k: N=174 ROI=-0.4421% delta=0.3358pp
- turnover<=2: N=285 ROI=-0.7737% delta=0.0042pp
- vol>=50k: N=359 ROI=-0.7779% delta=0.0pp
- liq>=100k: N=232 ROI=-0.7974% delta=-0.0195pp
- liq>=100k & vol>=50k: N=232 ROI=-0.7974% delta=-0.0195pp
- tx>=100: N=328 ROI=-0.8798% delta=-0.1019pp
- vol>=25k: N=330 ROI=-0.9004% delta=-0.1225pp
- liq>=75k: N=286 ROI=-0.9964% delta=-0.2185pp

## Missed-star scan
- Candidates: 1165
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 71, 'LIQ_LT_15K': 1047, 'VOL_LT_15K': 723, 'TX_LT_50': 588}

Research only; validate prospectively before changing production gates.
