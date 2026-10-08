# Wallet500 Cohort Research

Generated: 2026-10-08T10:32:51.336610+00:00
Source snapshot: 2026-10-08T10:26:16.675922+00:00

## Baseline
- N=359 ROI=-0.831% P/L=$-2.983302

## Best post-hoc counterfactuals (min 5 retained)
- liq>=250k: N=128 ROI=-0.3864% delta=0.4446pp
- liq>=500k: N=174 ROI=-0.4421% delta=0.3889pp
- turnover<=1: N=193 ROI=-0.5393% delta=0.2917pp
- vol>=50k: N=359 ROI=-0.831% delta=0.0pp
- turnover<=2: N=285 ROI=-0.8405% delta=-0.0095pp
- liq>=100k: N=232 ROI=-0.8795% delta=-0.0485pp
- liq>=100k & vol>=50k: N=232 ROI=-0.8795% delta=-0.0485pp
- tx>=100: N=328 ROI=-0.9379% delta=-0.1069pp
- vol>=25k: N=330 ROI=-0.9581% delta=-0.1271pp
- liq>=75k: N=286 ROI=-1.0631% delta=-0.2321pp

## Missed-star scan
- Candidates: 1165
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 71, 'LIQ_LT_15K': 1047, 'VOL_LT_15K': 723, 'TX_LT_50': 588}

Research only; validate prospectively before changing production gates.
