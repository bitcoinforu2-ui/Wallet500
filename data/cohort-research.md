# Wallet500 Cohort Research

Generated: 2026-09-18T10:14:22.697949+00:00
Source snapshot: 2026-09-18T10:07:54.769853+00:00

## Baseline
- N=359 ROI=-0.8067% P/L=$-2.895955

## Best post-hoc counterfactuals (min 5 retained)
- liq>=250k: N=128 ROI=-0.3864% delta=0.4203pp
- liq>=500k: N=174 ROI=-0.4421% delta=0.3646pp
- turnover<=1: N=193 ROI=-0.494% delta=0.3127pp
- vol>=50k: N=359 ROI=-0.8067% delta=0.0pp
- turnover<=2: N=285 ROI=-0.8099% delta=-0.0032pp
- liq>=100k: N=232 ROI=-0.8419% delta=-0.0352pp
- liq>=100k & vol>=50k: N=232 ROI=-0.8419% delta=-0.0352pp
- tx>=100: N=328 ROI=-0.9113% delta=-0.1046pp
- vol>=25k: N=330 ROI=-0.9316% delta=-0.1249pp
- liq>=75k: N=286 ROI=-1.0325% delta=-0.2258pp

## Missed-star scan
- Candidates: 1165
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 71, 'LIQ_LT_15K': 1047, 'VOL_LT_15K': 723, 'TX_LT_50': 588}

Research only; validate prospectively before changing production gates.
