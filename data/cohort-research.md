# Wallet500 Cohort Research

Generated: 2026-09-21T12:10:15.908492+00:00
Source snapshot: 2026-09-21T12:03:55.561888+00:00

## Baseline
- N=359 ROI=-0.7364% P/L=$-2.64371

## Best post-hoc counterfactuals (min 5 retained)
- turnover<=1: N=193 ROI=-0.3633% delta=0.3731pp
- liq>=250k: N=128 ROI=-0.3864% delta=0.35pp
- liq>=500k: N=174 ROI=-0.4421% delta=0.2943pp
- turnover<=2: N=285 ROI=-0.7214% delta=0.015pp
- liq>=100k: N=232 ROI=-0.7332% delta=0.0032pp
- liq>=100k & vol>=50k: N=232 ROI=-0.7332% delta=0.0032pp
- vol>=50k: N=359 ROI=-0.7364% delta=0.0pp
- tx>=100: N=328 ROI=-0.8344% delta=-0.098pp
- vol>=25k: N=330 ROI=-0.8552% delta=-0.1188pp
- liq>=75k: N=286 ROI=-0.9443% delta=-0.2079pp

## Missed-star scan
- Candidates: 1165
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 71, 'LIQ_LT_15K': 1047, 'VOL_LT_15K': 723, 'TX_LT_50': 588}

Research only; validate prospectively before changing production gates.
