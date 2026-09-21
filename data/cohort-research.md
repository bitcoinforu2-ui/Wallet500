# Wallet500 Cohort Research

Generated: 2026-09-21T00:58:09.421336+00:00
Source snapshot: 2026-09-21T00:51:43.595829+00:00

## Baseline
- N=359 ROI=-0.7375% P/L=$-2.647792

## Best post-hoc counterfactuals (min 5 retained)
- turnover<=1: N=193 ROI=-0.3654% delta=0.3721pp
- liq>=250k: N=128 ROI=-0.3864% delta=0.3511pp
- liq>=500k: N=174 ROI=-0.4421% delta=0.2954pp
- turnover<=2: N=285 ROI=-0.7228% delta=0.0147pp
- liq>=100k: N=232 ROI=-0.7349% delta=0.0026pp
- liq>=100k & vol>=50k: N=232 ROI=-0.7349% delta=0.0026pp
- vol>=50k: N=359 ROI=-0.7375% delta=0.0pp
- tx>=100: N=328 ROI=-0.8356% delta=-0.0981pp
- vol>=25k: N=330 ROI=-0.8564% delta=-0.1189pp
- liq>=75k: N=286 ROI=-0.9458% delta=-0.2083pp

## Missed-star scan
- Candidates: 1165
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 71, 'LIQ_LT_15K': 1047, 'VOL_LT_15K': 723, 'TX_LT_50': 588}

Research only; validate prospectively before changing production gates.
