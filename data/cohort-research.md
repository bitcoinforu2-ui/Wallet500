# Wallet500 Cohort Research

Generated: 2026-09-21T04:02:08.147066+00:00
Source snapshot: 2026-09-21T03:55:37.292755+00:00

## Baseline
- N=359 ROI=-0.7382% P/L=$-2.650241

## Best post-hoc counterfactuals (min 5 retained)
- turnover<=1: N=193 ROI=-0.3667% delta=0.3715pp
- liq>=250k: N=128 ROI=-0.3864% delta=0.3518pp
- liq>=500k: N=174 ROI=-0.4421% delta=0.2961pp
- turnover<=2: N=285 ROI=-0.7237% delta=0.0145pp
- liq>=100k: N=232 ROI=-0.736% delta=0.0022pp
- liq>=100k & vol>=50k: N=232 ROI=-0.736% delta=0.0022pp
- vol>=50k: N=359 ROI=-0.7382% delta=0.0pp
- tx>=100: N=328 ROI=-0.8364% delta=-0.0982pp
- vol>=25k: N=330 ROI=-0.8572% delta=-0.119pp
- liq>=75k: N=286 ROI=-0.9466% delta=-0.2084pp

## Missed-star scan
- Candidates: 1165
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 71, 'LIQ_LT_15K': 1047, 'VOL_LT_15K': 723, 'TX_LT_50': 588}

Research only; validate prospectively before changing production gates.
