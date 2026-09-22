# Wallet500 Cohort Research

Generated: 2026-09-22T08:56:43.016289+00:00
Source snapshot: 2026-09-22T08:49:49.315474+00:00

## Baseline
- N=359 ROI=-0.7425% P/L=$-2.665751

## Best post-hoc counterfactuals (min 5 retained)
- turnover<=1: N=193 ROI=-0.3747% delta=0.3678pp
- liq>=250k: N=128 ROI=-0.3864% delta=0.3561pp
- liq>=500k: N=174 ROI=-0.4421% delta=0.3004pp
- turnover<=2: N=285 ROI=-0.7291% delta=0.0134pp
- vol>=50k: N=359 ROI=-0.7425% delta=0.0pp
- liq>=100k: N=232 ROI=-0.7427% delta=-0.0002pp
- liq>=100k & vol>=50k: N=232 ROI=-0.7427% delta=-0.0002pp
- tx>=100: N=328 ROI=-0.8411% delta=-0.0986pp
- vol>=25k: N=330 ROI=-0.8619% delta=-0.1194pp
- liq>=75k: N=286 ROI=-0.952% delta=-0.2095pp

## Missed-star scan
- Candidates: 1165
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 71, 'LIQ_LT_15K': 1047, 'VOL_LT_15K': 723, 'TX_LT_50': 588}

Research only; validate prospectively before changing production gates.
