# Wallet500 Cohort Research

Generated: 2026-10-02T01:01:13.652307+00:00
Source snapshot: 2026-10-02T00:54:19.321544+00:00

## Baseline
- N=359 ROI=-0.7994% P/L=$-2.869833

## Best post-hoc counterfactuals (min 5 retained)
- liq>=250k: N=128 ROI=-0.3864% delta=0.413pp
- liq>=500k: N=174 ROI=-0.4421% delta=0.3573pp
- turnover<=1: N=193 ROI=-0.4805% delta=0.3189pp
- vol>=50k: N=359 ROI=-0.7994% delta=0.0pp
- turnover<=2: N=285 ROI=-0.8007% delta=-0.0013pp
- liq>=100k: N=232 ROI=-0.8306% delta=-0.0312pp
- liq>=100k & vol>=50k: N=232 ROI=-0.8306% delta=-0.0312pp
- tx>=100: N=328 ROI=-0.9033% delta=-0.1039pp
- vol>=25k: N=330 ROI=-0.9237% delta=-0.1243pp
- liq>=75k: N=286 ROI=-1.0234% delta=-0.224pp

## Missed-star scan
- Candidates: 1165
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 71, 'LIQ_LT_15K': 1047, 'VOL_LT_15K': 723, 'TX_LT_50': 588}

Research only; validate prospectively before changing production gates.
