# Wallet500 Cohort Research

Generated: 2026-09-18T03:38:55.910680+00:00
Source snapshot: 2026-09-18T03:32:16.782007+00:00

## Baseline
- N=359 ROI=-0.8069% P/L=$-2.896772

## Best post-hoc counterfactuals (min 5 retained)
- liq>=250k: N=128 ROI=-0.3864% delta=0.4205pp
- liq>=500k: N=174 ROI=-0.4421% delta=0.3648pp
- turnover<=1: N=193 ROI=-0.4944% delta=0.3125pp
- vol>=50k: N=359 ROI=-0.8069% delta=0.0pp
- turnover<=2: N=285 ROI=-0.8102% delta=-0.0033pp
- liq>=100k: N=232 ROI=-0.8422% delta=-0.0353pp
- liq>=100k & vol>=50k: N=232 ROI=-0.8422% delta=-0.0353pp
- tx>=100: N=328 ROI=-0.9115% delta=-0.1046pp
- vol>=25k: N=330 ROI=-0.9319% delta=-0.125pp
- liq>=75k: N=286 ROI=-1.0328% delta=-0.2259pp

## Missed-star scan
- Candidates: 1165
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 71, 'LIQ_LT_15K': 1047, 'VOL_LT_15K': 723, 'TX_LT_50': 588}

Research only; validate prospectively before changing production gates.
