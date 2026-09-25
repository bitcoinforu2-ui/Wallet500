# Wallet500 Cohort Research

Generated: 2026-09-25T03:28:36.906283+00:00
Source snapshot: 2026-09-25T03:22:09.143577+00:00

## Baseline
- N=359 ROI=-0.7713% P/L=$-2.769017

## Best post-hoc counterfactuals (min 5 retained)
- liq>=250k: N=128 ROI=-0.3864% delta=0.3849pp
- turnover<=1: N=193 ROI=-0.4282% delta=0.3431pp
- liq>=500k: N=174 ROI=-0.4421% delta=0.3292pp
- turnover<=2: N=285 ROI=-0.7654% delta=0.0059pp
- vol>=50k: N=359 ROI=-0.7713% delta=0.0pp
- liq>=100k: N=232 ROI=-0.7872% delta=-0.0159pp
- liq>=100k & vol>=50k: N=232 ROI=-0.7872% delta=-0.0159pp
- tx>=100: N=328 ROI=-0.8726% delta=-0.1013pp
- vol>=25k: N=330 ROI=-0.8932% delta=-0.1219pp
- liq>=75k: N=286 ROI=-0.9882% delta=-0.2169pp

## Missed-star scan
- Candidates: 1165
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 71, 'LIQ_LT_15K': 1047, 'VOL_LT_15K': 723, 'TX_LT_50': 588}

Research only; validate prospectively before changing production gates.
