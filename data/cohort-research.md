# Wallet500 Cohort Research

Generated: 2026-09-20T07:25:56.485377+00:00
Source snapshot: 2026-09-20T07:19:42.808510+00:00

## Baseline
- N=359 ROI=-1.0299% P/L=$-3.69718

## Best post-hoc counterfactuals (min 5 retained)
- liq>=250k: N=128 ROI=-0.3864% delta=0.6435pp
- turnover<=1: N=193 ROI=-0.391% delta=0.6389pp
- liq>=500k: N=174 ROI=-0.4421% delta=0.5878pp
- liq>=100k: N=232 ROI=-0.7562% delta=0.2737pp
- liq>=100k & vol>=50k: N=232 ROI=-0.7562% delta=0.2737pp
- liq>=75k: N=286 ROI=-0.963% delta=0.0669pp
- tx>=500: N=184 ROI=-0.9963% delta=0.0336pp
- tx>=250: N=283 ROI=-1.0011% delta=0.0288pp
- vol>=50k: N=359 ROI=-1.0299% delta=0.0pp
- liq>=100k & tx>=250: N=182 ROI=-1.0387% delta=-0.0088pp

## Missed-star scan
- Candidates: 1165
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 71, 'LIQ_LT_15K': 1047, 'VOL_LT_15K': 723, 'TX_LT_50': 588}

Research only; validate prospectively before changing production gates.
