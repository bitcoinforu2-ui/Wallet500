# Wallet500 Cohort Research

Generated: 2026-09-25T04:40:58.282674+00:00
Source snapshot: 2026-09-25T04:34:35.634958+00:00

## Baseline
- N=359 ROI=-0.7753% P/L=$-2.783302

## Best post-hoc counterfactuals (min 5 retained)
- liq>=250k: N=128 ROI=-0.3864% delta=0.3889pp
- turnover<=1: N=193 ROI=-0.4356% delta=0.3397pp
- liq>=500k: N=174 ROI=-0.4421% delta=0.3332pp
- turnover<=2: N=285 ROI=-0.7704% delta=0.0049pp
- vol>=50k: N=359 ROI=-0.7753% delta=0.0pp
- liq>=100k: N=232 ROI=-0.7933% delta=-0.018pp
- liq>=100k & vol>=50k: N=232 ROI=-0.7933% delta=-0.018pp
- tx>=100: N=328 ROI=-0.8769% delta=-0.1016pp
- vol>=25k: N=330 ROI=-0.8975% delta=-0.1222pp
- liq>=75k: N=286 ROI=-0.9931% delta=-0.2178pp

## Missed-star scan
- Candidates: 1165
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 71, 'LIQ_LT_15K': 1047, 'VOL_LT_15K': 723, 'TX_LT_50': 588}

Research only; validate prospectively before changing production gates.
