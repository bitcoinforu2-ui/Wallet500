# Wallet500 Cohort Research

Generated: 2026-09-23T10:28:32.827323+00:00
Source snapshot: 2026-09-23T10:22:03.108686+00:00

## Baseline
- N=359 ROI=-0.7503% P/L=$-2.693506

## Best post-hoc counterfactuals (min 5 retained)
- liq>=250k: N=128 ROI=-0.3864% delta=0.3639pp
- turnover<=1: N=193 ROI=-0.3891% delta=0.3612pp
- liq>=500k: N=174 ROI=-0.4421% delta=0.3082pp
- turnover<=2: N=285 ROI=-0.7389% delta=0.0114pp
- vol>=50k: N=359 ROI=-0.7503% delta=0.0pp
- liq>=100k: N=232 ROI=-0.7546% delta=-0.0043pp
- liq>=100k & vol>=50k: N=232 ROI=-0.7546% delta=-0.0043pp
- tx>=100: N=328 ROI=-0.8495% delta=-0.0992pp
- vol>=25k: N=330 ROI=-0.8703% delta=-0.12pp
- liq>=75k: N=286 ROI=-0.9618% delta=-0.2115pp

## Missed-star scan
- Candidates: 1165
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 71, 'LIQ_LT_15K': 1047, 'VOL_LT_15K': 723, 'TX_LT_50': 588}

Research only; validate prospectively before changing production gates.
