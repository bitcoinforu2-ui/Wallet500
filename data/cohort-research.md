# Wallet500 Cohort Research

Generated: 2026-10-02T18:15:28.752239+00:00
Source snapshot: 2026-10-02T18:08:49.314268+00:00

## Baseline
- N=359 ROI=-0.7995% P/L=$-2.870241

## Best post-hoc counterfactuals (min 5 retained)
- liq>=250k: N=128 ROI=-0.3864% delta=0.4131pp
- liq>=500k: N=174 ROI=-0.4421% delta=0.3574pp
- turnover<=1: N=193 ROI=-0.4807% delta=0.3188pp
- vol>=50k: N=359 ROI=-0.7995% delta=0.0pp
- turnover<=2: N=285 ROI=-0.8009% delta=-0.0014pp
- liq>=100k: N=232 ROI=-0.8308% delta=-0.0313pp
- liq>=100k & vol>=50k: N=232 ROI=-0.8308% delta=-0.0313pp
- tx>=100: N=328 ROI=-0.9034% delta=-0.1039pp
- vol>=25k: N=330 ROI=-0.9239% delta=-0.1244pp
- liq>=75k: N=286 ROI=-1.0235% delta=-0.224pp

## Missed-star scan
- Candidates: 1165
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 71, 'LIQ_LT_15K': 1047, 'VOL_LT_15K': 723, 'TX_LT_50': 588}

Research only; validate prospectively before changing production gates.
