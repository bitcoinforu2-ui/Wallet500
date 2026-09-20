# Wallet500 Cohort Research

Generated: 2026-09-20T21:04:36.594809+00:00
Source snapshot: 2026-09-20T20:58:33.062895+00:00

## Baseline
- N=359 ROI=-0.7433% P/L=$-2.668608

## Best post-hoc counterfactuals (min 5 retained)
- turnover<=1: N=193 ROI=-0.3762% delta=0.3671pp
- liq>=250k: N=128 ROI=-0.3864% delta=0.3569pp
- liq>=500k: N=174 ROI=-0.4421% delta=0.3012pp
- turnover<=2: N=285 ROI=-0.7301% delta=0.0132pp
- vol>=50k: N=359 ROI=-0.7433% delta=0.0pp
- liq>=100k: N=232 ROI=-0.7439% delta=-0.0006pp
- liq>=100k & vol>=50k: N=232 ROI=-0.7439% delta=-0.0006pp
- tx>=100: N=328 ROI=-0.842% delta=-0.0987pp
- vol>=25k: N=330 ROI=-0.8628% delta=-0.1195pp
- liq>=75k: N=286 ROI=-0.953% delta=-0.2097pp

## Missed-star scan
- Candidates: 1165
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 71, 'LIQ_LT_15K': 1047, 'VOL_LT_15K': 723, 'TX_LT_50': 588}

Research only; validate prospectively before changing production gates.
