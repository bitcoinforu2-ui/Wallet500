# Wallet500 Cohort Research

Generated: 2026-09-20T14:51:51.856093+00:00
Source snapshot: 2026-09-20T14:45:59.704687+00:00

## Baseline
- N=359 ROI=-1.0309% P/L=$-3.700853

## Best post-hoc counterfactuals (min 5 retained)
- liq>=250k: N=128 ROI=-0.3864% delta=0.6445pp
- turnover<=1: N=193 ROI=-0.3929% delta=0.638pp
- liq>=500k: N=174 ROI=-0.4421% delta=0.5888pp
- liq>=100k: N=232 ROI=-0.7578% delta=0.2731pp
- liq>=100k & vol>=50k: N=232 ROI=-0.7578% delta=0.2731pp
- liq>=75k: N=286 ROI=-0.9643% delta=0.0666pp
- tx>=500: N=184 ROI=-0.9983% delta=0.0326pp
- tx>=250: N=283 ROI=-1.0024% delta=0.0285pp
- vol>=50k: N=359 ROI=-1.0309% delta=0.0pp
- liq>=100k & tx>=250: N=182 ROI=-1.0407% delta=-0.0098pp

## Missed-star scan
- Candidates: 1165
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 71, 'LIQ_LT_15K': 1047, 'VOL_LT_15K': 723, 'TX_LT_50': 588}

Research only; validate prospectively before changing production gates.
