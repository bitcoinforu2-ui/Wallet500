# Wallet500 Cohort Research

Generated: 2026-09-20T20:37:56.397279+00:00
Source snapshot: 2026-09-20T20:30:58.675292+00:00

## Baseline
- N=359 ROI=-1.0219% P/L=$-3.668608

## Best post-hoc counterfactuals (min 5 retained)
- turnover<=1: N=193 ROI=-0.3762% delta=0.6457pp
- liq>=250k: N=128 ROI=-0.3864% delta=0.6355pp
- liq>=500k: N=174 ROI=-0.4421% delta=0.5798pp
- liq>=100k: N=232 ROI=-0.7439% delta=0.278pp
- liq>=100k & vol>=50k: N=232 ROI=-0.7439% delta=0.278pp
- liq>=75k: N=286 ROI=-0.953% delta=0.0689pp
- tx>=500: N=184 ROI=-0.9808% delta=0.0411pp
- tx>=250: N=283 ROI=-0.991% delta=0.0309pp
- vol>=50k: N=359 ROI=-1.0219% delta=0.0pp
- liq>=100k & tx>=250: N=182 ROI=-1.023% delta=-0.0011pp

## Missed-star scan
- Candidates: 1165
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 71, 'LIQ_LT_15K': 1047, 'VOL_LT_15K': 723, 'TX_LT_50': 588}

Research only; validate prospectively before changing production gates.
