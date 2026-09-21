# Wallet500 Cohort Research

Generated: 2026-09-21T09:29:55.132774+00:00
Source snapshot: 2026-09-21T09:23:09.833689+00:00

## Baseline
- N=359 ROI=-0.7372% P/L=$-2.646568

## Best post-hoc counterfactuals (min 5 retained)
- turnover<=1: N=193 ROI=-0.3648% delta=0.3724pp
- liq>=250k: N=128 ROI=-0.3864% delta=0.3508pp
- liq>=500k: N=174 ROI=-0.4421% delta=0.2951pp
- turnover<=2: N=285 ROI=-0.7224% delta=0.0148pp
- liq>=100k: N=232 ROI=-0.7344% delta=0.0028pp
- liq>=100k & vol>=50k: N=232 ROI=-0.7344% delta=0.0028pp
- vol>=50k: N=359 ROI=-0.7372% delta=0.0pp
- tx>=100: N=328 ROI=-0.8352% delta=-0.098pp
- vol>=25k: N=330 ROI=-0.8561% delta=-0.1189pp
- liq>=75k: N=286 ROI=-0.9453% delta=-0.2081pp

## Missed-star scan
- Candidates: 1165
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 71, 'LIQ_LT_15K': 1047, 'VOL_LT_15K': 723, 'TX_LT_50': 588}

Research only; validate prospectively before changing production gates.
