# Wallet500 Cohort Research

Generated: 2026-09-15T08:08:25.578941+00:00
Source snapshot: 2026-09-15T08:01:58.968447+00:00

## Baseline
- N=359 ROI=-0.8116% P/L=$-2.913506

## Best post-hoc counterfactuals (min 5 retained)
- liq>=250k: N=128 ROI=-0.3864% delta=0.4252pp
- liq>=500k: N=174 ROI=-0.4421% delta=0.3695pp
- turnover<=1: N=193 ROI=-0.5031% delta=0.3085pp
- vol>=50k: N=359 ROI=-0.8116% delta=0.0pp
- turnover<=2: N=285 ROI=-0.8161% delta=-0.0045pp
- liq>=100k: N=232 ROI=-0.8494% delta=-0.0378pp
- liq>=100k & vol>=50k: N=232 ROI=-0.8494% delta=-0.0378pp
- tx>=100: N=328 ROI=-0.9166% delta=-0.105pp
- vol>=25k: N=330 ROI=-0.937% delta=-0.1254pp
- liq>=75k: N=286 ROI=-1.0387% delta=-0.2271pp

## Missed-star scan
- Candidates: 1165
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 71, 'LIQ_LT_15K': 1047, 'VOL_LT_15K': 723, 'TX_LT_50': 588}

Research only; validate prospectively before changing production gates.
