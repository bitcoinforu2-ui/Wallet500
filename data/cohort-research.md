# Wallet500 Cohort Research

Generated: 2026-10-07T23:54:24.779615+00:00
Source snapshot: 2026-10-07T23:47:49.319113+00:00

## Baseline
- N=359 ROI=-0.8308% P/L=$-2.982486

## Best post-hoc counterfactuals (min 5 retained)
- liq>=250k: N=128 ROI=-0.3864% delta=0.4444pp
- liq>=500k: N=174 ROI=-0.4421% delta=0.3887pp
- turnover<=1: N=193 ROI=-0.5388% delta=0.292pp
- vol>=50k: N=359 ROI=-0.8308% delta=0.0pp
- turnover<=2: N=285 ROI=-0.8403% delta=-0.0095pp
- liq>=100k: N=232 ROI=-0.8792% delta=-0.0484pp
- liq>=100k & vol>=50k: N=232 ROI=-0.8792% delta=-0.0484pp
- tx>=100: N=328 ROI=-0.9377% delta=-0.1069pp
- vol>=25k: N=330 ROI=-0.9579% delta=-0.1271pp
- liq>=75k: N=286 ROI=-1.0628% delta=-0.232pp

## Missed-star scan
- Candidates: 1165
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 71, 'LIQ_LT_15K': 1047, 'VOL_LT_15K': 723, 'TX_LT_50': 588}

Research only; validate prospectively before changing production gates.
