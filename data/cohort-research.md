# Wallet500 Cohort Research

Generated: 2026-09-20T06:04:14.851171+00:00
Source snapshot: 2026-09-20T05:57:44.300077+00:00

## Baseline
- N=359 ROI=-1.0321% P/L=$-3.705343

## Best post-hoc counterfactuals (min 5 retained)
- liq>=250k: N=128 ROI=-0.3864% delta=0.6457pp
- turnover<=1: N=193 ROI=-0.3952% delta=0.6369pp
- liq>=500k: N=174 ROI=-0.4421% delta=0.59pp
- liq>=100k: N=232 ROI=-0.7597% delta=0.2724pp
- liq>=100k & vol>=50k: N=232 ROI=-0.7597% delta=0.2724pp
- liq>=75k: N=286 ROI=-0.9659% delta=0.0662pp
- tx>=500: N=184 ROI=-1.0008% delta=0.0313pp
- tx>=250: N=283 ROI=-1.004% delta=0.0281pp
- vol>=50k: N=359 ROI=-1.0321% delta=0.0pp
- liq>=100k & tx>=250: N=182 ROI=-1.0432% delta=-0.0111pp

## Missed-star scan
- Candidates: 1165
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 71, 'LIQ_LT_15K': 1047, 'VOL_LT_15K': 723, 'TX_LT_50': 588}

Research only; validate prospectively before changing production gates.
