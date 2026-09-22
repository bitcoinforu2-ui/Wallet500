# Wallet500 Cohort Research

Generated: 2026-09-22T08:09:12.840189+00:00
Source snapshot: 2026-09-22T08:02:27.014756+00:00

## Baseline
- N=359 ROI=-0.7416% P/L=$-2.662486

## Best post-hoc counterfactuals (min 5 retained)
- turnover<=1: N=193 ROI=-0.373% delta=0.3686pp
- liq>=250k: N=128 ROI=-0.3864% delta=0.3552pp
- liq>=500k: N=174 ROI=-0.4421% delta=0.2995pp
- turnover<=2: N=285 ROI=-0.728% delta=0.0136pp
- liq>=100k: N=232 ROI=-0.7412% delta=0.0004pp
- liq>=100k & vol>=50k: N=232 ROI=-0.7412% delta=0.0004pp
- vol>=50k: N=359 ROI=-0.7416% delta=0.0pp
- tx>=100: N=328 ROI=-0.8401% delta=-0.0985pp
- vol>=25k: N=330 ROI=-0.8609% delta=-0.1193pp
- liq>=75k: N=286 ROI=-0.9509% delta=-0.2093pp

## Missed-star scan
- Candidates: 1165
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 71, 'LIQ_LT_15K': 1047, 'VOL_LT_15K': 723, 'TX_LT_50': 588}

Research only; validate prospectively before changing production gates.
