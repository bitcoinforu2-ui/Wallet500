# Wallet500 Cohort Research

Generated: 2026-09-13T17:03:52.816935+00:00
Source snapshot: 2026-09-13T16:57:18.309002+00:00

## Baseline
- N=359 ROI=-0.8092% P/L=$-2.904935

## Best post-hoc counterfactuals (min 5 retained)
- liq>=250k: N=128 ROI=-0.3864% delta=0.4228pp
- liq>=500k: N=174 ROI=-0.4421% delta=0.3671pp
- turnover<=1: N=193 ROI=-0.4987% delta=0.3105pp
- vol>=50k: N=359 ROI=-0.8092% delta=0.0pp
- turnover<=2: N=285 ROI=-0.813% delta=-0.0038pp
- liq>=100k: N=232 ROI=-0.8458% delta=-0.0366pp
- liq>=100k & vol>=50k: N=232 ROI=-0.8458% delta=-0.0366pp
- tx>=100: N=328 ROI=-0.914% delta=-0.1048pp
- vol>=25k: N=330 ROI=-0.9344% delta=-0.1252pp
- liq>=75k: N=286 ROI=-1.0357% delta=-0.2265pp

## Missed-star scan
- Candidates: 1165
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 71, 'LIQ_LT_15K': 1047, 'VOL_LT_15K': 723, 'TX_LT_50': 588}

Research only; validate prospectively before changing production gates.
