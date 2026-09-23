# Wallet500 Cohort Research

Generated: 2026-09-23T15:29:46.870638+00:00
Source snapshot: 2026-09-23T15:23:15.708568+00:00

## Baseline
- N=359 ROI=-0.7506% P/L=$-2.694731

## Best post-hoc counterfactuals (min 5 retained)
- liq>=250k: N=128 ROI=-0.3864% delta=0.3642pp
- turnover<=1: N=193 ROI=-0.3897% delta=0.3609pp
- liq>=500k: N=174 ROI=-0.4421% delta=0.3085pp
- turnover<=2: N=285 ROI=-0.7393% delta=0.0113pp
- vol>=50k: N=359 ROI=-0.7506% delta=0.0pp
- liq>=100k: N=232 ROI=-0.7551% delta=-0.0045pp
- liq>=100k & vol>=50k: N=232 ROI=-0.7551% delta=-0.0045pp
- tx>=100: N=328 ROI=-0.8499% delta=-0.0993pp
- vol>=25k: N=330 ROI=-0.8707% delta=-0.1201pp
- liq>=75k: N=286 ROI=-0.9622% delta=-0.2116pp

## Missed-star scan
- Candidates: 1165
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 71, 'LIQ_LT_15K': 1047, 'VOL_LT_15K': 723, 'TX_LT_50': 588}

Research only; validate prospectively before changing production gates.
