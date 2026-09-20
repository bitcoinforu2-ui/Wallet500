# Wallet500 Cohort Research

Generated: 2026-09-20T09:04:51.716627+00:00
Source snapshot: 2026-09-20T08:58:33.717265+00:00

## Baseline
- N=359 ROI=-1.0335% P/L=$-3.710241

## Best post-hoc counterfactuals (min 5 retained)
- liq>=250k: N=128 ROI=-0.3864% delta=0.6471pp
- turnover<=1: N=193 ROI=-0.3978% delta=0.6357pp
- liq>=500k: N=174 ROI=-0.4421% delta=0.5914pp
- liq>=100k: N=232 ROI=-0.7618% delta=0.2717pp
- liq>=100k & vol>=50k: N=232 ROI=-0.7618% delta=0.2717pp
- liq>=75k: N=286 ROI=-0.9676% delta=0.0659pp
- tx>=500: N=184 ROI=-1.0034% delta=0.0301pp
- tx>=250: N=283 ROI=-1.0057% delta=0.0278pp
- vol>=50k: N=359 ROI=-1.0335% delta=0.0pp
- liq>=100k & tx>=250: N=182 ROI=-1.0458% delta=-0.0123pp

## Missed-star scan
- Candidates: 1165
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 71, 'LIQ_LT_15K': 1047, 'VOL_LT_15K': 723, 'TX_LT_50': 588}

Research only; validate prospectively before changing production gates.
