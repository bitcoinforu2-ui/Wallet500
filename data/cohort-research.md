# Wallet500 Cohort Research

Generated: 2026-09-14T18:54:48.564118+00:00
Source snapshot: 2026-09-14T18:48:28.796753+00:00

## Baseline
- N=359 ROI=-0.8094% P/L=$-2.905751

## Best post-hoc counterfactuals (min 5 retained)
- liq>=250k: N=128 ROI=-0.3864% delta=0.423pp
- liq>=500k: N=174 ROI=-0.4421% delta=0.3673pp
- turnover<=1: N=193 ROI=-0.4991% delta=0.3103pp
- vol>=50k: N=359 ROI=-0.8094% delta=0.0pp
- turnover<=2: N=285 ROI=-0.8133% delta=-0.0039pp
- liq>=100k: N=232 ROI=-0.8461% delta=-0.0367pp
- liq>=100k & vol>=50k: N=232 ROI=-0.8461% delta=-0.0367pp
- tx>=100: N=328 ROI=-0.9143% delta=-0.1049pp
- vol>=25k: N=330 ROI=-0.9346% delta=-0.1252pp
- liq>=75k: N=286 ROI=-1.036% delta=-0.2266pp

## Missed-star scan
- Candidates: 1165
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 71, 'LIQ_LT_15K': 1047, 'VOL_LT_15K': 723, 'TX_LT_50': 588}

Research only; validate prospectively before changing production gates.
