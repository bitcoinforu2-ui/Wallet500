# Wallet500 Cohort Research

Generated: 2026-09-18T18:29:31.333966+00:00
Source snapshot: 2026-09-18T18:22:59.255098+00:00

## Baseline
- N=359 ROI=-0.7978% P/L=$-2.864119

## Best post-hoc counterfactuals (min 5 retained)
- liq>=250k: N=128 ROI=-0.3864% delta=0.4114pp
- liq>=500k: N=174 ROI=-0.4421% delta=0.3557pp
- turnover<=1: N=193 ROI=-0.4775% delta=0.3203pp
- vol>=50k: N=359 ROI=-0.7978% delta=0.0pp
- turnover<=2: N=285 ROI=-0.7987% delta=-0.0009pp
- liq>=100k: N=232 ROI=-0.8282% delta=-0.0304pp
- liq>=100k & vol>=50k: N=232 ROI=-0.8282% delta=-0.0304pp
- tx>=100: N=328 ROI=-0.9016% delta=-0.1038pp
- vol>=25k: N=330 ROI=-0.922% delta=-0.1242pp
- liq>=75k: N=286 ROI=-1.0214% delta=-0.2236pp

## Missed-star scan
- Candidates: 1165
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 71, 'LIQ_LT_15K': 1047, 'VOL_LT_15K': 723, 'TX_LT_50': 588}

Research only; validate prospectively before changing production gates.
