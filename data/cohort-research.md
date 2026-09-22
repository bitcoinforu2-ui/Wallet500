# Wallet500 Cohort Research

Generated: 2026-09-22T13:29:51.853906+00:00
Source snapshot: 2026-09-22T13:23:18.582750+00:00

## Baseline
- N=359 ROI=-0.7428% P/L=$-2.666568

## Best post-hoc counterfactuals (min 5 retained)
- turnover<=1: N=193 ROI=-0.3752% delta=0.3676pp
- liq>=250k: N=128 ROI=-0.3864% delta=0.3564pp
- liq>=500k: N=174 ROI=-0.4421% delta=0.3007pp
- turnover<=2: N=285 ROI=-0.7294% delta=0.0134pp
- vol>=50k: N=359 ROI=-0.7428% delta=0.0pp
- liq>=100k: N=232 ROI=-0.743% delta=-0.0002pp
- liq>=100k & vol>=50k: N=232 ROI=-0.743% delta=-0.0002pp
- tx>=100: N=328 ROI=-0.8413% delta=-0.0985pp
- vol>=25k: N=330 ROI=-0.8621% delta=-0.1193pp
- liq>=75k: N=286 ROI=-0.9523% delta=-0.2095pp

## Missed-star scan
- Candidates: 1165
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 71, 'LIQ_LT_15K': 1047, 'VOL_LT_15K': 723, 'TX_LT_50': 588}

Research only; validate prospectively before changing production gates.
