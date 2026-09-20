# Wallet500 Cohort Research

Generated: 2026-09-20T04:40:12.394845+00:00
Source snapshot: 2026-09-20T04:33:08.284268+00:00

## Baseline
- N=359 ROI=-1.0325% P/L=$-3.706568

## Best post-hoc counterfactuals (min 5 retained)
- liq>=250k: N=128 ROI=-0.3864% delta=0.6461pp
- turnover<=1: N=193 ROI=-0.3959% delta=0.6366pp
- liq>=500k: N=174 ROI=-0.4421% delta=0.5904pp
- liq>=100k: N=232 ROI=-0.7602% delta=0.2723pp
- liq>=100k & vol>=50k: N=232 ROI=-0.7602% delta=0.2723pp
- liq>=75k: N=286 ROI=-0.9663% delta=0.0662pp
- tx>=500: N=184 ROI=-1.0014% delta=0.0311pp
- tx>=250: N=283 ROI=-1.0044% delta=0.0281pp
- vol>=50k: N=359 ROI=-1.0325% delta=0.0pp
- liq>=100k & tx>=250: N=182 ROI=-1.0438% delta=-0.0113pp

## Missed-star scan
- Candidates: 1165
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 71, 'LIQ_LT_15K': 1047, 'VOL_LT_15K': 723, 'TX_LT_50': 588}

Research only; validate prospectively before changing production gates.
