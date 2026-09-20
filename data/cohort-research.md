# Wallet500 Cohort Research

Generated: 2026-09-20T03:54:34.250146+00:00
Source snapshot: 2026-09-20T03:48:22.065801+00:00

## Baseline
- N=359 ROI=-1.0328% P/L=$-3.707792

## Best post-hoc counterfactuals (min 5 retained)
- liq>=250k: N=128 ROI=-0.3864% delta=0.6464pp
- turnover<=1: N=193 ROI=-0.3965% delta=0.6363pp
- liq>=500k: N=174 ROI=-0.4421% delta=0.5907pp
- liq>=100k: N=232 ROI=-0.7608% delta=0.272pp
- liq>=100k & vol>=50k: N=232 ROI=-0.7608% delta=0.272pp
- liq>=75k: N=286 ROI=-0.9667% delta=0.0661pp
- tx>=500: N=184 ROI=-1.0021% delta=0.0307pp
- tx>=250: N=283 ROI=-1.0049% delta=0.0279pp
- vol>=50k: N=359 ROI=-1.0328% delta=0.0pp
- liq>=100k & tx>=250: N=182 ROI=-1.0445% delta=-0.0117pp

## Missed-star scan
- Candidates: 1165
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 71, 'LIQ_LT_15K': 1047, 'VOL_LT_15K': 723, 'TX_LT_50': 588}

Research only; validate prospectively before changing production gates.
