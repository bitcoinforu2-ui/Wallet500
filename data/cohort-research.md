# Wallet500 Cohort Research

Generated: 2026-09-15T13:45:15.865881+00:00
Source snapshot: 2026-09-15T13:38:51.145313+00:00

## Baseline
- N=359 ROI=-0.8112% P/L=$-2.912282

## Best post-hoc counterfactuals (min 5 retained)
- liq>=250k: N=128 ROI=-0.3864% delta=0.4248pp
- liq>=500k: N=174 ROI=-0.4421% delta=0.3691pp
- turnover<=1: N=193 ROI=-0.5025% delta=0.3087pp
- vol>=50k: N=359 ROI=-0.8112% delta=0.0pp
- turnover<=2: N=285 ROI=-0.8156% delta=-0.0044pp
- liq>=100k: N=232 ROI=-0.8489% delta=-0.0377pp
- liq>=100k & vol>=50k: N=232 ROI=-0.8489% delta=-0.0377pp
- tx>=100: N=328 ROI=-0.9162% delta=-0.105pp
- vol>=25k: N=330 ROI=-0.9366% delta=-0.1254pp
- liq>=75k: N=286 ROI=-1.0382% delta=-0.227pp

## Missed-star scan
- Candidates: 1165
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 71, 'LIQ_LT_15K': 1047, 'VOL_LT_15K': 723, 'TX_LT_50': 588}

Research only; validate prospectively before changing production gates.
