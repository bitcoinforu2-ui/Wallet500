# Wallet500 Cohort Research

Generated: 2026-09-21T14:08:53.017570+00:00
Source snapshot: 2026-09-21T14:01:56.315469+00:00

## Baseline
- N=359 ROI=-0.7357% P/L=$-2.641262

## Best post-hoc counterfactuals (min 5 retained)
- turnover<=1: N=193 ROI=-0.362% delta=0.3737pp
- liq>=250k: N=128 ROI=-0.3864% delta=0.3493pp
- liq>=500k: N=174 ROI=-0.4421% delta=0.2936pp
- turnover<=2: N=285 ROI=-0.7205% delta=0.0152pp
- liq>=100k: N=232 ROI=-0.7321% delta=0.0036pp
- liq>=100k & vol>=50k: N=232 ROI=-0.7321% delta=0.0036pp
- vol>=50k: N=359 ROI=-0.7357% delta=0.0pp
- tx>=100: N=328 ROI=-0.8336% delta=-0.0979pp
- vol>=25k: N=330 ROI=-0.8545% delta=-0.1188pp
- liq>=75k: N=286 ROI=-0.9435% delta=-0.2078pp

## Missed-star scan
- Candidates: 1165
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 71, 'LIQ_LT_15K': 1047, 'VOL_LT_15K': 723, 'TX_LT_50': 588}

Research only; validate prospectively before changing production gates.
