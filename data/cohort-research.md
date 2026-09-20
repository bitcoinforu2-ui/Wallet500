# Wallet500 Cohort Research

Generated: 2026-09-20T01:38:02.941151+00:00
Source snapshot: 2026-09-20T01:31:50.942817+00:00

## Baseline
- N=359 ROI=-1.0077% P/L=$-3.617588

## Best post-hoc counterfactuals (min 5 retained)
- turnover<=1: N=193 ROI=-0.3498% delta=0.6579pp
- liq>=250k: N=128 ROI=-0.3864% delta=0.6213pp
- liq>=500k: N=174 ROI=-0.4421% delta=0.5656pp
- liq>=100k: N=232 ROI=-0.7219% delta=0.2858pp
- liq>=100k & vol>=50k: N=232 ROI=-0.7219% delta=0.2858pp
- liq>=75k: N=286 ROI=-0.9352% delta=0.0725pp
- tx>=500: N=184 ROI=-0.9531% delta=0.0546pp
- tx>=250: N=283 ROI=-0.973% delta=0.0347pp
- liq>=100k & tx>=250: N=182 ROI=-0.9949% delta=0.0128pp
- vol>=50k: N=359 ROI=-1.0077% delta=0.0pp

## Missed-star scan
- Candidates: 1165
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 71, 'LIQ_LT_15K': 1047, 'VOL_LT_15K': 723, 'TX_LT_50': 588}

Research only; validate prospectively before changing production gates.
