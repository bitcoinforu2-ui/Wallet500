# Wallet500 Cohort Research

Generated: 2026-09-24T04:06:54.225766+00:00
Source snapshot: 2026-09-24T04:00:32.200129+00:00

## Baseline
- N=359 ROI=-0.756% P/L=$-2.713915

## Best post-hoc counterfactuals (min 5 retained)
- liq>=250k: N=128 ROI=-0.3864% delta=0.3696pp
- turnover<=1: N=193 ROI=-0.3997% delta=0.3563pp
- liq>=500k: N=174 ROI=-0.4421% delta=0.3139pp
- turnover<=2: N=285 ROI=-0.746% delta=0.01pp
- vol>=50k: N=359 ROI=-0.756% delta=0.0pp
- liq>=100k: N=232 ROI=-0.7634% delta=-0.0074pp
- liq>=100k & vol>=50k: N=232 ROI=-0.7634% delta=-0.0074pp
- tx>=100: N=328 ROI=-0.8558% delta=-0.0998pp
- vol>=25k: N=330 ROI=-0.8765% delta=-0.1205pp
- liq>=75k: N=286 ROI=-0.9689% delta=-0.2129pp

## Missed-star scan
- Candidates: 1165
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 71, 'LIQ_LT_15K': 1047, 'VOL_LT_15K': 723, 'TX_LT_50': 588}

Research only; validate prospectively before changing production gates.
