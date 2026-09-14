# Wallet500 Cohort Research

Generated: 2026-09-14T05:54:13.728388+00:00
Source snapshot: 2026-09-14T05:47:23.283858+00:00

## Baseline
- N=359 ROI=-0.8086% P/L=$-2.902894

## Best post-hoc counterfactuals (min 5 retained)
- liq>=250k: N=128 ROI=-0.3864% delta=0.4222pp
- liq>=500k: N=174 ROI=-0.4421% delta=0.3665pp
- turnover<=1: N=193 ROI=-0.4976% delta=0.311pp
- vol>=50k: N=359 ROI=-0.8086% delta=0.0pp
- turnover<=2: N=285 ROI=-0.8123% delta=-0.0037pp
- liq>=100k: N=232 ROI=-0.8449% delta=-0.0363pp
- liq>=100k & vol>=50k: N=232 ROI=-0.8449% delta=-0.0363pp
- tx>=100: N=328 ROI=-0.9134% delta=-0.1048pp
- vol>=25k: N=330 ROI=-0.9338% delta=-0.1252pp
- liq>=75k: N=286 ROI=-1.035% delta=-0.2264pp

## Missed-star scan
- Candidates: 1165
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 71, 'LIQ_LT_15K': 1047, 'VOL_LT_15K': 723, 'TX_LT_50': 588}

Research only; validate prospectively before changing production gates.
