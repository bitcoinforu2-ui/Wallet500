# Wallet500 Cohort Research

Generated: 2026-09-18T21:53:13.871589+00:00
Source snapshot: 2026-09-18T21:46:44.482077+00:00

## Baseline
- N=359 ROI=-0.7891% P/L=$-2.83269

## Best post-hoc counterfactuals (min 5 retained)
- liq>=250k: N=128 ROI=-0.3864% delta=0.4027pp
- liq>=500k: N=174 ROI=-0.4421% delta=0.347pp
- turnover<=1: N=193 ROI=-0.4612% delta=0.3279pp
- turnover<=2: N=285 ROI=-0.7877% delta=0.0014pp
- vol>=50k: N=359 ROI=-0.7891% delta=0.0pp
- liq>=100k: N=232 ROI=-0.8146% delta=-0.0255pp
- liq>=100k & vol>=50k: N=232 ROI=-0.8146% delta=-0.0255pp
- tx>=100: N=328 ROI=-0.892% delta=-0.1029pp
- vol>=25k: N=330 ROI=-0.9125% delta=-0.1234pp
- liq>=75k: N=286 ROI=-1.0104% delta=-0.2213pp

## Missed-star scan
- Candidates: 1165
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 71, 'LIQ_LT_15K': 1047, 'VOL_LT_15K': 723, 'TX_LT_50': 588}

Research only; validate prospectively before changing production gates.
