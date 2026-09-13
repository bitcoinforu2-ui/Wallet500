# Wallet500 Cohort Research

Generated: 2026-09-13T12:51:56.861757+00:00
Source snapshot: 2026-09-13T12:46:03.537891+00:00

## Baseline
- N=359 ROI=-0.8063% P/L=$-2.894731

## Best post-hoc counterfactuals (min 5 retained)
- liq>=250k: N=128 ROI=-0.3864% delta=0.4199pp
- liq>=500k: N=174 ROI=-0.4421% delta=0.3642pp
- turnover<=1: N=193 ROI=-0.4934% delta=0.3129pp
- vol>=50k: N=359 ROI=-0.8063% delta=0.0pp
- turnover<=2: N=285 ROI=-0.8095% delta=-0.0032pp
- liq>=100k: N=232 ROI=-0.8414% delta=-0.0351pp
- liq>=100k & vol>=50k: N=232 ROI=-0.8414% delta=-0.0351pp
- tx>=100: N=328 ROI=-0.9109% delta=-0.1046pp
- vol>=25k: N=330 ROI=-0.9313% delta=-0.125pp
- liq>=75k: N=286 ROI=-1.0321% delta=-0.2258pp

## Missed-star scan
- Candidates: 1165
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 71, 'LIQ_LT_15K': 1047, 'VOL_LT_15K': 723, 'TX_LT_50': 588}

Research only; validate prospectively before changing production gates.
