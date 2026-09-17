# Wallet500 Cohort Research

Generated: 2026-09-17T05:08:18.011566+00:00
Source snapshot: 2026-09-17T05:01:50.096997+00:00

## Baseline
- N=359 ROI=-0.8107% P/L=$-2.910241

## Best post-hoc counterfactuals (min 5 retained)
- liq>=250k: N=128 ROI=-0.3864% delta=0.4243pp
- liq>=500k: N=174 ROI=-0.4421% delta=0.3686pp
- turnover<=1: N=193 ROI=-0.5014% delta=0.3093pp
- vol>=50k: N=359 ROI=-0.8107% delta=0.0pp
- turnover<=2: N=285 ROI=-0.8149% delta=-0.0042pp
- liq>=100k: N=232 ROI=-0.848% delta=-0.0373pp
- liq>=100k & vol>=50k: N=232 ROI=-0.848% delta=-0.0373pp
- tx>=100: N=328 ROI=-0.9156% delta=-0.1049pp
- vol>=25k: N=330 ROI=-0.936% delta=-0.1253pp
- liq>=75k: N=286 ROI=-1.0375% delta=-0.2268pp

## Missed-star scan
- Candidates: 1165
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 71, 'LIQ_LT_15K': 1047, 'VOL_LT_15K': 723, 'TX_LT_50': 588}

Research only; validate prospectively before changing production gates.
