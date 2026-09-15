# Wallet500 Cohort Research

Generated: 2026-09-15T15:41:24.136239+00:00
Source snapshot: 2026-09-15T15:35:03.432299+00:00

## Baseline
- N=359 ROI=-0.8099% P/L=$-2.907384

## Best post-hoc counterfactuals (min 5 retained)
- liq>=250k: N=128 ROI=-0.3864% delta=0.4235pp
- liq>=500k: N=174 ROI=-0.4421% delta=0.3678pp
- turnover<=1: N=193 ROI=-0.4999% delta=0.31pp
- vol>=50k: N=359 ROI=-0.8099% delta=0.0pp
- turnover<=2: N=285 ROI=-0.8139% delta=-0.004pp
- liq>=100k: N=232 ROI=-0.8468% delta=-0.0369pp
- liq>=100k & vol>=50k: N=232 ROI=-0.8468% delta=-0.0369pp
- tx>=100: N=328 ROI=-0.9148% delta=-0.1049pp
- vol>=25k: N=330 ROI=-0.9351% delta=-0.1252pp
- liq>=75k: N=286 ROI=-1.0365% delta=-0.2266pp

## Missed-star scan
- Candidates: 1165
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 71, 'LIQ_LT_15K': 1047, 'VOL_LT_15K': 723, 'TX_LT_50': 588}

Research only; validate prospectively before changing production gates.
