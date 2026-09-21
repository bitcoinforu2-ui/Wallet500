# Wallet500 Cohort Research

Generated: 2026-09-21T00:36:42.957411+00:00
Source snapshot: 2026-09-21T00:30:10.639781+00:00

## Baseline
- N=359 ROI=-0.7413% P/L=$-2.661262

## Best post-hoc counterfactuals (min 5 retained)
- turnover<=1: N=193 ROI=-0.3724% delta=0.3689pp
- liq>=250k: N=128 ROI=-0.3864% delta=0.3549pp
- liq>=500k: N=174 ROI=-0.4421% delta=0.2992pp
- turnover<=2: N=285 ROI=-0.7275% delta=0.0138pp
- liq>=100k: N=232 ROI=-0.7407% delta=0.0006pp
- liq>=100k & vol>=50k: N=232 ROI=-0.7407% delta=0.0006pp
- vol>=50k: N=359 ROI=-0.7413% delta=0.0pp
- tx>=100: N=328 ROI=-0.8397% delta=-0.0984pp
- vol>=25k: N=330 ROI=-0.8605% delta=-0.1192pp
- liq>=75k: N=286 ROI=-0.9505% delta=-0.2092pp

## Missed-star scan
- Candidates: 1165
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 71, 'LIQ_LT_15K': 1047, 'VOL_LT_15K': 723, 'TX_LT_50': 588}

Research only; validate prospectively before changing production gates.
