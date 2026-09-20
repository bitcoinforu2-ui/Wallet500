# Wallet500 Cohort Research

Generated: 2026-09-20T03:27:09.368381+00:00
Source snapshot: 2026-09-20T03:20:57.848334+00:00

## Baseline
- N=359 ROI=-1.0123% P/L=$-3.634323

## Best post-hoc counterfactuals (min 5 retained)
- turnover<=1: N=193 ROI=-0.3584% delta=0.6539pp
- liq>=250k: N=128 ROI=-0.3864% delta=0.6259pp
- liq>=500k: N=174 ROI=-0.4421% delta=0.5702pp
- liq>=100k: N=232 ROI=-0.7291% delta=0.2832pp
- liq>=100k & vol>=50k: N=232 ROI=-0.7291% delta=0.2832pp
- liq>=75k: N=286 ROI=-0.9411% delta=0.0712pp
- tx>=500: N=184 ROI=-0.9622% delta=0.0501pp
- tx>=250: N=283 ROI=-0.9789% delta=0.0334pp
- liq>=100k & tx>=250: N=182 ROI=-1.0041% delta=0.0082pp
- vol>=50k: N=359 ROI=-1.0123% delta=0.0pp

## Missed-star scan
- Candidates: 1165
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 71, 'LIQ_LT_15K': 1047, 'VOL_LT_15K': 723, 'TX_LT_50': 588}

Research only; validate prospectively before changing production gates.
