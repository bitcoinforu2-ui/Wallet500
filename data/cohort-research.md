# Wallet500 Cohort Research

Generated: 2026-09-20T06:50:26.834267+00:00
Source snapshot: 2026-09-20T06:44:11.616451+00:00

## Baseline
- N=359 ROI=-1.032% P/L=$-3.704935

## Best post-hoc counterfactuals (min 5 retained)
- liq>=250k: N=128 ROI=-0.3864% delta=0.6456pp
- turnover<=1: N=193 ROI=-0.395% delta=0.637pp
- liq>=500k: N=174 ROI=-0.4421% delta=0.5899pp
- liq>=100k: N=232 ROI=-0.7595% delta=0.2725pp
- liq>=100k & vol>=50k: N=232 ROI=-0.7595% delta=0.2725pp
- liq>=75k: N=286 ROI=-0.9657% delta=0.0663pp
- tx>=500: N=184 ROI=-1.0006% delta=0.0314pp
- tx>=250: N=283 ROI=-1.0039% delta=0.0281pp
- vol>=50k: N=359 ROI=-1.032% delta=0.0pp
- liq>=100k & tx>=250: N=182 ROI=-1.0429% delta=-0.0109pp

## Missed-star scan
- Candidates: 1165
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 71, 'LIQ_LT_15K': 1047, 'VOL_LT_15K': 723, 'TX_LT_50': 588}

Research only; validate prospectively before changing production gates.
