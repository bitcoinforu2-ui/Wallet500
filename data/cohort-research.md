# Wallet500 Cohort Research

Generated: 2026-09-28T01:59:29.032354+00:00
Source snapshot: 2026-09-28T01:52:52.066193+00:00

## Baseline
- N=359 ROI=-0.7821% P/L=$-2.807792

## Best post-hoc counterfactuals (min 5 retained)
- liq>=250k: N=128 ROI=-0.3864% delta=0.3957pp
- liq>=500k: N=174 ROI=-0.4421% delta=0.34pp
- turnover<=1: N=193 ROI=-0.4483% delta=0.3338pp
- turnover<=2: N=285 ROI=-0.779% delta=0.0031pp
- vol>=50k: N=359 ROI=-0.7821% delta=0.0pp
- liq>=100k: N=232 ROI=-0.8039% delta=-0.0218pp
- liq>=100k & vol>=50k: N=232 ROI=-0.8039% delta=-0.0218pp
- tx>=100: N=328 ROI=-0.8844% delta=-0.1023pp
- vol>=25k: N=330 ROI=-0.9049% delta=-0.1228pp
- liq>=75k: N=286 ROI=-1.0017% delta=-0.2196pp

## Missed-star scan
- Candidates: 1165
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 71, 'LIQ_LT_15K': 1047, 'VOL_LT_15K': 723, 'TX_LT_50': 588}

Research only; validate prospectively before changing production gates.
