# Wallet500 Cohort Research

Generated: 2026-09-29T23:10:49.920560+00:00
Source snapshot: 2026-09-29T23:04:19.044592+00:00

## Baseline
- N=359 ROI=-0.8005% P/L=$-2.873915

## Best post-hoc counterfactuals (min 5 retained)
- liq>=250k: N=128 ROI=-0.3864% delta=0.4141pp
- liq>=500k: N=174 ROI=-0.4421% delta=0.3584pp
- turnover<=1: N=193 ROI=-0.4826% delta=0.3179pp
- vol>=50k: N=359 ROI=-0.8005% delta=0.0pp
- turnover<=2: N=285 ROI=-0.8022% delta=-0.0017pp
- liq>=100k: N=232 ROI=-0.8324% delta=-0.0319pp
- liq>=100k & vol>=50k: N=232 ROI=-0.8324% delta=-0.0319pp
- tx>=100: N=328 ROI=-0.9045% delta=-0.104pp
- vol>=25k: N=330 ROI=-0.925% delta=-0.1245pp
- liq>=75k: N=286 ROI=-1.0248% delta=-0.2243pp

## Missed-star scan
- Candidates: 1165
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 71, 'LIQ_LT_15K': 1047, 'VOL_LT_15K': 723, 'TX_LT_50': 588}

Research only; validate prospectively before changing production gates.
