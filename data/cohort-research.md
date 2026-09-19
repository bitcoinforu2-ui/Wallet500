# Wallet500 Cohort Research

Generated: 2026-09-19T03:26:14.527643+00:00
Source snapshot: 2026-09-19T03:19:28.893428+00:00

## Baseline
- N=359 ROI=-0.7737% P/L=$-2.777588

## Best post-hoc counterfactuals (min 5 retained)
- liq>=250k: N=128 ROI=-0.3864% delta=0.3873pp
- turnover<=1: N=193 ROI=-0.4327% delta=0.341pp
- liq>=500k: N=174 ROI=-0.4421% delta=0.3316pp
- turnover<=2: N=285 ROI=-0.7684% delta=0.0053pp
- vol>=50k: N=359 ROI=-0.7737% delta=0.0pp
- liq>=100k: N=232 ROI=-0.7909% delta=-0.0172pp
- liq>=100k & vol>=50k: N=232 ROI=-0.7909% delta=-0.0172pp
- tx>=100: N=328 ROI=-0.8752% delta=-0.1015pp
- vol>=25k: N=330 ROI=-0.8958% delta=-0.1221pp
- liq>=75k: N=286 ROI=-0.9912% delta=-0.2175pp

## Missed-star scan
- Candidates: 1165
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 71, 'LIQ_LT_15K': 1047, 'VOL_LT_15K': 723, 'TX_LT_50': 588}

Research only; validate prospectively before changing production gates.
